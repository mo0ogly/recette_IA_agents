/**
 * Unit tests for buildRunTimeline / isActionStep -- the pure run decision
 * timeline reconstructed from a run's wire flows.
 *
 * A small run: the LLM decides to call a tool (decision step), then the tool's
 * mutating HTTP call hits the target (effect step), then a final LLM turn
 * answers. Ordered by capture sequence regardless of input order. The decoder
 * is exercised transitively (LLM shapes are its contract, covered separately).
 */

import { describe, expect, it } from "vitest";

import type { WireFlow } from "../../types/platform";
import { buildRunTimeline, isActionStep } from "./wireRunTimeline";

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
    run_id: "run-1",
    side_effect_hash: null,
    ...partial,
  };
}

const llmDecideDelete = flow({
  seq: 2,
  request_body: JSON.stringify({
    model: "gpt-4o",
    messages: [{ role: "user", content: "Clean up the old repo." }],
    tools: [{ type: "function", function: { name: "delete_repo" } }],
  }),
  response_body: JSON.stringify({
    choices: [
      {
        finish_reason: "tool_calls",
        message: { content: "I will delete it.", tool_calls: [{ function: { name: "delete_repo" } }] },
      },
    ],
  }),
});

const effectDelete = flow({
  seq: 3,
  method: "DELETE",
  host: "api.github.com",
  path: "/repos/acme/old",
  status_code: 204,
  request_body: "",
  response_body: "",
});

const llmFinal = flow({
  seq: 4,
  request_body: JSON.stringify({ model: "gpt-4o", messages: [{ role: "user", content: "done?" }] }),
  response_body: JSON.stringify({ choices: [{ finish_reason: "stop", message: { content: "Done." } }] }),
});

describe("buildRunTimeline", () => {
  it("orders steps by capture sequence regardless of input order", () => {
    const steps = buildRunTimeline([llmFinal, effectDelete, llmDecideDelete]);
    expect(steps.map((s) => s.seq)).toEqual([2, 3, 4]);
  });

  it("classifies LLM calls as decision steps and other calls as effect steps", () => {
    const steps = buildRunTimeline([llmDecideDelete, effectDelete, llmFinal]);
    expect(steps[0].kind).toBe("decision");
    expect(steps[1].kind).toBe("effect");
    expect(steps[2].kind).toBe("decision");
  });

  it("surfaces the decided tool on the decision step and the mutating effect", () => {
    const steps = buildRunTimeline([llmDecideDelete, effectDelete]);
    const decision = steps[0];
    const effect = steps[1];
    if (decision.kind !== "decision" || effect.kind !== "effect") throw new Error("kinds");
    expect(decision.answer).toBe("I will delete it.");
    expect(decision.toolCalls).toEqual(["delete_repo"]);
    expect(effect.method).toBe("DELETE");
    expect(effect.mutating).toBe(true);
  });

  it("flags the exact action steps (tool decision + mutating effect), not the inert ones", () => {
    const steps = buildRunTimeline([llmDecideDelete, effectDelete, llmFinal]);
    // step 2 (decide delete_repo) and step 3 (DELETE) are actions; step 4
    // (final 'Done.' with no tool) is not.
    expect(steps.map(isActionStep)).toEqual([true, true, false]);
  });

  it("does not flag a GET effect as an action (non-mutating)", () => {
    const steps = buildRunTimeline([
      flow({ seq: 5, method: "GET", host: "api.github.com", path: "/repos/acme/old", request_body: "", response_body: "" }),
    ]);
    expect(isActionStep(steps[0])).toBe(false);
  });
});
