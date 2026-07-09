/**
 * Unit tests for decodeLlmFlow -- the pure wire-flow -> LLM-exchange decoder.
 *
 * The payloads are the canonical public request/response shapes of the OpenAI
 * chat/completions and Anthropic messages APIs (the bytes a wire flow to those
 * hosts carries), plus a generic {messages:[...]} shape and negative cases
 * (non-LLM flow, truncated body). The decoder is pure, so a literal fixture is
 * the exact contract under test -- no backend, no mock.
 */

import { describe, expect, it } from "vitest";

import type { WireFlow } from "../../types/platform";
import { decodeLlmFlow } from "./wireLlmDecode";

/** Minimal WireFlow builder: only the fields the decoder reads matter. */
function flow(partial: Partial<WireFlow>): WireFlow {
  return {
    seq: 1,
    method: "POST",
    scheme: "https",
    host: "api.openai.com",
    port: 443,
    path: "/v1/chat/completions",
    status_code: 200,
    ok: true,
    content_type: "application/json",
    request_body: "",
    response_body: "",
    run_id: null,
    side_effect_hash: null,
    ...partial,
  };
}

describe("decodeLlmFlow", () => {
  it("decodes an OpenAI chat/completions flow (model, messages, tools, usage)", () => {
    const ex = decodeLlmFlow(
      flow({
        request_body: JSON.stringify({
          model: "gpt-4o",
          messages: [
            { role: "system", content: "You are a triage agent." },
            { role: "user", content: "Open a PR for issue 42." },
          ],
          tools: [{ type: "function", function: { name: "open_pr" } }],
        }),
        response_body: JSON.stringify({
          choices: [
            {
              finish_reason: "tool_calls",
              message: {
                content: null,
                tool_calls: [{ function: { name: "open_pr" } }],
              },
            },
          ],
          usage: { prompt_tokens: 31, completion_tokens: 12 },
        }),
      }),
    );
    expect(ex).not.toBeNull();
    expect(ex?.provider).toBe("openai");
    expect(ex?.model).toBe("gpt-4o");
    expect(ex?.messages).toHaveLength(2);
    expect(ex?.messages[0]).toEqual({ role: "system", text: "You are a triage agent." });
    expect(ex?.tools).toEqual(["open_pr"]);
    expect(ex?.toolCalls).toEqual(["open_pr"]);
    expect(ex?.usage).toEqual({ input: 31, output: 12 });
    expect(ex?.stop).toBe("tool_calls");
  });

  it("decodes an Anthropic messages flow (system outside messages, content blocks)", () => {
    const ex = decodeLlmFlow(
      flow({
        host: "api.anthropic.com",
        path: "/v1/messages",
        request_body: JSON.stringify({
          model: "claude-sonnet-4",
          system: "You are a SOC analyst.",
          messages: [
            {
              role: "user",
              content: [{ type: "text", text: "Is this alert malicious?" }],
            },
          ],
          tools: [{ name: "lookup_ioc" }],
        }),
        response_body: JSON.stringify({
          content: [
            { type: "text", text: "Likely benign." },
            { type: "tool_use", name: "lookup_ioc" },
          ],
          stop_reason: "tool_use",
          usage: { input_tokens: 55, output_tokens: 9 },
        }),
      }),
    );
    expect(ex?.provider).toBe("anthropic");
    expect(ex?.model).toBe("claude-sonnet-4");
    // system prompt is surfaced as the first message.
    expect(ex?.messages[0]).toEqual({ role: "system", text: "You are a SOC analyst." });
    expect(ex?.messages[1]).toEqual({ role: "user", text: "Is this alert malicious?" });
    expect(ex?.tools).toEqual(["lookup_ioc"]);
    expect(ex?.toolCalls).toEqual(["lookup_ioc"]);
    expect(ex?.responseText).toBe("Likely benign.");
    expect(ex?.usage).toEqual({ input: 55, output: 9 });
    expect(ex?.stop).toBe("tool_use");
  });

  it("decodes a generic {messages:[...]} flow on an unknown host as 'generic'", () => {
    const ex = decodeLlmFlow(
      flow({
        host: "llm.internal.lab",
        path: "/inference",
        request_body: JSON.stringify({
          model: "llama-3.3-70b",
          messages: [{ role: "user", content: "ping" }],
        }),
        response_body: JSON.stringify({
          choices: [{ message: { content: "pong" }, finish_reason: "stop" }],
        }),
      }),
    );
    expect(ex?.provider).toBe("generic");
    expect(ex?.model).toBe("llama-3.3-70b");
    expect(ex?.responseText).toBe("pong");
  });

  it("returns null for a non-LLM flow (no known path, no messages)", () => {
    const ex = decodeLlmFlow(
      flow({
        host: "api.github.com",
        path: "/repos/acme/app/pulls",
        request_body: JSON.stringify({ title: "Fix", head: "b", base: "main" }),
        response_body: JSON.stringify({ number: 42 }),
      }),
    );
    expect(ex).toBeNull();
  });

  it("returns null when the request body is truncated (unparseable), never a wrong decode", () => {
    const ex = decodeLlmFlow(
      flow({
        request_body: '{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}...[truncated]',
      }),
    );
    expect(ex).toBeNull();
  });

  it("still decodes the request when only the response is truncated (partial exchange)", () => {
    const ex = decodeLlmFlow(
      flow({
        request_body: JSON.stringify({
          model: "gpt-4o",
          messages: [{ role: "user", content: "hi" }],
        }),
        response_body: '{"choices":[{"message":{"content":"he...[truncated]',
      }),
    );
    expect(ex).not.toBeNull();
    expect(ex?.model).toBe("gpt-4o");
    expect(ex?.responseText).toBeNull(); // response unparseable -> no answer, but request read
  });
});
