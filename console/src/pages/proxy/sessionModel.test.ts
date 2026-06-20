import { describe, expect, it } from "vitest";

import type { ProxyTrace } from "../../types/platform";
import { groupSessions, sessionsFailed } from "./sessionModel";

/** Minimal trace factory: only the fields the model reads. */
function trace(over: Partial<ProxyTrace>): ProxyTrace {
  return {
    seq: 0,
    event_id: "e",
    timestamp: "t",
    agent_id: "a",
    target_system: "github",
    action_type: "read_repo",
    resource: "org/repo",
    request_payload: {},
    ok: true,
    status_code: 200,
    side_effect_hash: null,
    error: null,
    run_id: "r1",
    response: {},
    ...over,
  };
}

describe("groupSessions", () => {
  it("groups by run_id and keeps exchanges sorted by seq", () => {
    const traces = [
      trace({ seq: 3, run_id: "r1", agent_id: "a1" }),
      trace({ seq: 1, run_id: "r1", agent_id: "a1" }),
      trace({ seq: 2, run_id: "r2", agent_id: "a2" }),
    ];
    const sessions = groupSessions(traces, "run");
    expect(sessions.map((s) => s.key)).toEqual(["r1", "r2"]); // r1 lastSeq=3 first
    expect(sessions[0].exchanges.map((e) => e.seq)).toEqual([1, 3]);
    expect(sessions[0].total).toBe(2);
  });

  it("splits CONCURRENT interleaved runs without cross-contamination", () => {
    const traces = [
      trace({ seq: 1, run_id: "r1", agent_id: "a1" }),
      trace({ seq: 2, run_id: "r2", agent_id: "a2" }),
      trace({ seq: 3, run_id: "r1", agent_id: "a1" }),
      trace({ seq: 4, run_id: "r2", agent_id: "a2", ok: false, status_code: 500 }),
    ];
    const byRun = groupSessions(traces, "run");
    const r1 = byRun.find((s) => s.key === "r1")!;
    const r2 = byRun.find((s) => s.key === "r2")!;
    expect(r1.exchanges.map((e) => e.seq)).toEqual([1, 3]);
    expect(r2.exchanges.map((e) => e.seq)).toEqual([2, 4]);
    expect(r2.failed).toBe(1);
    expect(r1.failed).toBe(0);
  });

  it("orders sessions by lastSeq desc (most recently active on top)", () => {
    const traces = [
      trace({ seq: 1, run_id: "r1" }),
      trace({ seq: 5, run_id: "r2" }),
      trace({ seq: 2, run_id: "r1" }),
    ];
    expect(groupSessions(traces, "run").map((s) => s.key)).toEqual(["r2", "r1"]);
  });

  it("groups by agent and by agent_target", () => {
    const traces = [
      trace({ seq: 1, agent_id: "a1", target_system: "github", run_id: "r1" }),
      trace({ seq: 2, agent_id: "a1", target_system: "okta", run_id: "r1" }),
    ];
    expect(groupSessions(traces, "agent").map((s) => s.key)).toEqual(["a1"]);
    expect(groupSessions(traces, "agent").length).toBe(1);
    const at = groupSessions(traces, "agent_target");
    expect(at.map((s) => s.key).sort()).toEqual(["a1|github", "a1|okta"]);
  });

  it("maps each exchange to intent + response + hash", () => {
    const t = trace({
      seq: 7,
      action_type: "open_pr",
      resource: "org/repo",
      request_payload: { title: "x" },
      response: { number: 42 },
      side_effect_hash: "abc",
    });
    const ex = groupSessions([t], "run")[0].exchanges[0];
    expect(ex.intent).toEqual({ action_type: "open_pr", resource: "org/repo", payload: { title: "x" } });
    expect(ex.response).toEqual({ status_code: 200, ok: true, body: { number: 42 } });
    expect(ex.hash).toBe("abc");
  });

  it("buckets a null run_id under a stable label without throwing", () => {
    const sessions = groupSessions([trace({ seq: 1, run_id: null })], "run");
    expect(sessions).toHaveLength(1);
    expect(sessions[0].exchanges).toHaveLength(1);
  });

  it("sums failed exchanges across sessions via sessionsFailed", () => {
    const traces = [
      trace({ seq: 1, run_id: "r1", ok: true, status_code: 200 }),
      trace({ seq: 2, run_id: "r1", ok: false, status_code: 500 }),
      trace({ seq: 3, run_id: "r2", ok: true, status_code: 200 }),
    ];
    const sessions = groupSessions(traces, "run");
    // One failed exchange in r1, none in r2 -> total 1.
    expect(sessions.find((s) => s.key === "r1")!.failed).toBe(1);
    expect(sessions.find((s) => s.key === "r2")!.failed).toBe(0);
    expect(sessionsFailed(sessions)).toBe(1);
  });

  it("tie-breaks equal lastSeq by firstSeq asc (smaller firstSeq first)", () => {
    // r1: firstSeq=1, lastSeq=10 ; r2: firstSeq=4, lastSeq=10 (same lastSeq).
    const traces = [
      trace({ seq: 1, run_id: "r1" }),
      trace({ seq: 10, run_id: "r1" }),
      trace({ seq: 4, run_id: "r2" }),
      trace({ seq: 10, run_id: "r2" }),
    ];
    const sessions = groupSessions(traces, "run");
    expect(sessions.map((s) => s.lastSeq)).toEqual([10, 10]);
    expect(sessions.map((s) => s.key)).toEqual(["r1", "r2"]); // firstSeq 1 < 4
  });
});
