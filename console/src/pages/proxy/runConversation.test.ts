/**
 * Unit tests for buildRunConversation -- the pure join of LLM decisions and the
 * agent<->server exchanges they produced, into one ordered conversation.
 */

import { describe, expect, it } from "vitest";

import type { LlmTrace } from "../../api/client";
import type { ProxyTrace } from "../../types/platform";
import { buildRunConversation } from "./runConversation";

function llm(partial: Partial<LlmTrace>): LlmTrace {
  return {
    seq: 1,
    event_id: "e",
    agent_id: "a1",
    model: "gpt-4o",
    kind: "tool_call",
    tool_name: "read_repo",
    resource: "acme/x",
    intent: "read acme/x",
    prompt_tokens: 10,
    completion_tokens: 5,
    total_tokens: 15,
    latency_ms: 0,
    error: null,
    ...partial,
  };
}

function trace(partial: Partial<ProxyTrace>): ProxyTrace {
  return {
    seq: 1,
    event_id: "e",
    timestamp: "t",
    agent_id: "a1",
    target_system: "github",
    action_type: "read_repo",
    resource: "acme/x",
    request_payload: {},
    ok: true,
    status_code: 200,
    side_effect_hash: null,
    error: null,
    run_id: "run-1",
    response: {},
    ...partial,
  };
}

describe("buildRunConversation", () => {
  it("joins a tool decision with the server exchange it produced (request + response)", () => {
    const turns = buildRunConversation(
      [
        llm({ seq: 1, kind: "tool_call", tool_name: "read_repo", resource: "acme/x" }),
        llm({ seq: 2, kind: "final", tool_name: null, resource: "" }),
      ],
      [trace({ seq: 1, action_type: "read_repo", resource: "acme/x", response: { number: 42 }, status_code: 200 })],
    );
    expect(turns).toHaveLength(2);
    // Turn 1: the LLM thought (decision) + the resulting server exchange.
    expect(turns[0].decisionKind).toBe("tool_call");
    expect(turns[0].tool).toBe("read_repo");
    expect(turns[0].tokens).toEqual({ prompt: 10, completion: 5, total: 15 });
    expect(turns[0].exchange).not.toBeNull();
    expect(turns[0].exchange?.response).toEqual({ number: 42 });
    expect(turns[0].exchange?.status).toBe(200);
    // Turn 2: a final decision has no server exchange.
    expect(turns[1].decisionKind).toBe("final");
    expect(turns[1].exchange).toBeNull();
    expect(turns.map((t) => t.step)).toEqual([1, 2]);
  });

  it("leaves a denied tool decision (no matching server trace) without an exchange", () => {
    const turns = buildRunConversation(
      [llm({ seq: 1, kind: "tool_call", tool_name: "delete_repo", resource: "acme/x" })],
      [], // the action never reached a server (denied) -> no proxy trace
    );
    expect(turns).toHaveLength(1);
    expect(turns[0].tool).toBe("delete_repo");
    expect(turns[0].exchange).toBeNull();
  });

  it("appends a server trace with no matching decision as an exchange-only turn (never dropped)", () => {
    const turns = buildRunConversation(
      [llm({ seq: 1, kind: "final", tool_name: null, resource: "" })],
      [trace({ seq: 1, action_type: "open_pr", resource: "acme/y", response: { url: "z" } })],
    );
    expect(turns).toHaveLength(2);
    const exchangeOnly = turns.find((t) => t.decisionKind === null);
    expect(exchangeOnly).toBeDefined();
    expect(exchangeOnly?.exchange?.actionType).toBe("open_pr");
    expect(exchangeOnly?.exchange?.response).toEqual({ url: "z" });
  });

  it("orders turns by capture sequence regardless of input order", () => {
    const turns = buildRunConversation(
      [
        llm({ seq: 3, kind: "final", tool_name: null, resource: "" }),
        llm({ seq: 1, kind: "tool_call", resource: "acme/a" }),
        llm({ seq: 2, kind: "tool_call", resource: "acme/b" }),
      ],
      [
        trace({ seq: 2, resource: "acme/b" }),
        trace({ seq: 1, resource: "acme/a" }),
      ],
    );
    expect(turns.map((t) => t.seq)).toEqual([1, 2, 3]);
  });
});
