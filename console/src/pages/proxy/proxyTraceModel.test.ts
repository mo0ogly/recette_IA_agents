/**
 * Unit tests for the pure proxy-trace helpers (Monaco-free).
 *
 * Asserted against the real captured fixture so the serialization and summary
 * rules match the exact payload shape the backend returns.
 */

import { describe, expect, it } from "vitest";
import type { ProxyTrace, ProxyTraceResponse } from "../../types/platform";
import tracesFixture from "./__fixtures__/traces.fixture.json";
import {
  distinctValues,
  failureCount,
  filterTraces,
  isEmptyFilter,
  traceJson,
  tracesToJsonl,
  traceToLine,
} from "./proxyTraceModel";

const traces = (tracesFixture as ProxyTraceResponse).traces;

function failing(): ProxyTrace {
  return { ...traces[0], seq: 99, ok: false, status_code: 503, error: "boom", side_effect_hash: null };
}

describe("traceToLine", () => {
  it("summarises a successful trace with an ok outcome", () => {
    const line = traceToLine(traces[0]);
    expect(line.outcome).toBe("ok");
    expect(line.seq).toBe(traces[0].seq);
    expect(line.label).toContain("list_repos");
    expect(line.label).toContain("github/acme/widgets");
    expect(line.label).toContain("200");
  });

  it("marks a failed trace as fail", () => {
    expect(traceToLine(failing()).outcome).toBe("fail");
  });

  it("exposes structured fields for a scannable line", () => {
    const line = traceToLine(traces[0]);
    expect(line.actionType).toBe(traces[0].action_type);
    expect(line.target).toBe(traces[0].target_system);
    expect(line.resource).toBe(traces[0].resource);
    expect(line.statusCode).toBe(traces[0].status_code);
  });
});

describe("traceJson", () => {
  it("pretty-prints the selected trace exactly (no key drift)", () => {
    expect(traceJson(traces, traces[0].seq)).toBe(JSON.stringify(traces[0], null, 2));
  });

  it("returns a hint when nothing is selected", () => {
    expect(traceJson(traces, null)).toMatch(/select a trace/);
  });

  it("returns a hint when the seq aged out of the buffer", () => {
    expect(traceJson(traces, 9999)).toMatch(/no such trace/);
  });
});

describe("tracesToJsonl", () => {
  it("emits one compact JSON line per trace in order", () => {
    const jsonl = tracesToJsonl(traces);
    const lines = jsonl.split("\n");
    expect(lines).toHaveLength(traces.length);
    expect(JSON.parse(lines[0]).seq).toBe(traces[0].seq);
  });
});

describe("failureCount", () => {
  it("counts only failed traces", () => {
    expect(failureCount(traces)).toBe(0);
    expect(failureCount([...traces, failing()])).toBe(1);
  });
});

describe("filterTraces", () => {
  const mixed: ProxyTrace[] = [
    { ...traces[0], seq: 1, agent_id: "a1", target_system: "github" },
    { ...traces[0], seq: 2, agent_id: "a2", target_system: "github" },
    { ...traces[0], seq: 3, agent_id: "a1", target_system: "gitlab" },
  ];

  it("is a pass-through on an empty filter", () => {
    expect(isEmptyFilter({})).toBe(true);
    expect(filterTraces(mixed, {})).toBe(mixed);
  });

  it("filters by outcome (ok vs fail)", () => {
    const withFail: ProxyTrace[] = [
      { ...traces[0], seq: 1, ok: true },
      { ...traces[0], seq: 2, ok: false, status_code: 503 },
      { ...traces[0], seq: 3, ok: true },
    ];
    expect(isEmptyFilter({ outcome: "fail" })).toBe(false);
    expect(filterTraces(withFail, { outcome: "fail" }).map((t) => t.seq)).toEqual([2]);
    expect(filterTraces(withFail, { outcome: "ok" }).map((t) => t.seq)).toEqual([1, 3]);
  });

  it("filters by agent_id", () => {
    expect(filterTraces(mixed, { agentId: "a1" }).map((t) => t.seq)).toEqual([1, 3]);
  });

  it("filters by target_system", () => {
    expect(filterTraces(mixed, { targetSystem: "gitlab" }).map((t) => t.seq)).toEqual([3]);
  });

  it("ANDs both clauses and preserves seq order", () => {
    expect(
      filterTraces(mixed, { agentId: "a1", targetSystem: "github" }).map((t) => t.seq),
    ).toEqual([1]);
  });
});

describe("distinctValues", () => {
  const mixed: ProxyTrace[] = [
    { ...traces[0], agent_id: "b", target_system: "github" },
    { ...traces[0], agent_id: "a", target_system: "github" },
    { ...traces[0], agent_id: "a", target_system: "gitlab" },
  ];

  it("returns sorted distinct agent ids", () => {
    expect(distinctValues(mixed, "agent_id")).toEqual(["a", "b"]);
  });

  it("returns sorted distinct target systems", () => {
    expect(distinctValues(mixed, "target_system")).toEqual(["github", "gitlab"]);
  });
});
