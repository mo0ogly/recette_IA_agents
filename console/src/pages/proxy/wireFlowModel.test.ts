import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import { distinctWireValues, filterWireFlows, isEmptyWireFilter, maxDuration } from "./wireFlowModel";

function wire(over: Partial<WireFlow>): WireFlow {
  return { seq:1, method:"POST", scheme:"http", host:"127.0.0.1", port:9101,
    path:"/github/execute", status_code:200, ok:true, content_type:"application/json",
    request_body:'{"action":"read_repo"}', response_body:'{"ok":true}', run_id:"r1",
    side_effect_hash:"H1", ...over };
}

describe("filterWireFlows", () => {
  const flows = [
    wire({ seq:1, host:"127.0.0.1", method:"POST", status_code:200, run_id:"r1", path:"/github/execute" }),
    wire({ seq:2, host:"example.com", method:"GET", status_code:404, run_id:"r2", path:"/x", request_body:"", response_body:"nope" }),
  ];
  it("empty filter passes through", () => {
    expect(filterWireFlows(flows, {})).toHaveLength(2);
    expect(isEmptyWireFilter({})).toBe(true);
  });
  it("filters by host / method / status / run", () => {
    expect(filterWireFlows(flows, { host:"example.com" }).map(f=>f.seq)).toEqual([2]);
    expect(filterWireFlows(flows, { method:"POST" }).map(f=>f.seq)).toEqual([1]);
    expect(filterWireFlows(flows, { status:"404" }).map(f=>f.seq)).toEqual([2]);
    expect(filterWireFlows(flows, { runId:"r1" }).map(f=>f.seq)).toEqual([1]);
  });
  it("free text matches path + bodies (case-insensitive)", () => {
    expect(filterWireFlows(flows, { text:"READ_REPO" }).map(f=>f.seq)).toEqual([1]);
    expect(filterWireFlows(flows, { text:"nope" }).map(f=>f.seq)).toEqual([2]);
    expect(filterWireFlows(flows, { text:"/github" }).map(f=>f.seq)).toEqual([1]);
  });
  it("distinctWireValues lists options sorted", () => {
    expect(distinctWireValues(flows, "host")).toEqual(["127.0.0.1","example.com"]);
    expect(distinctWireValues(flows, "method")).toEqual(["GET","POST"]);
    expect(distinctWireValues(flows, "run_id")).toEqual(["r1","r2"]);
  });
});

describe("filterWireFlows by tracking identity", () => {
  // session_id/instance_id are server-provided optional fields (see wireLayers).
  const tracked = [
    wire({ seq:1, ...( { session_id:"s1", instance_id:"attacker" } as object) }),
    wire({ seq:2, ...( { session_id:"s2", instance_id:"attacker" } as object) }),
    wire({ seq:3, ...( { session_id:"s2", instance_id:"auditor" } as object) }),
  ];
  it("follows one instance across the sessions it acted in", () => {
    expect(filterWireFlows(tracked, { instanceId:"attacker" }).map(f=>f.seq)).toEqual([1,2]);
  });
  it("narrows to one session + instance", () => {
    expect(filterWireFlows(tracked, { sessionId:"s2", instanceId:"auditor" }).map(f=>f.seq)).toEqual([3]);
  });
  it("tracking clauses count toward isEmptyWireFilter", () => {
    expect(isEmptyWireFilter({ instanceId:"attacker" })).toBe(false);
    expect(isEmptyWireFilter({ sessionId:"s1" })).toBe(false);
  });
});

describe("maxDuration", () => {
  it("returns 0 when no flow carries a duration", () => {
    expect(maxDuration([wire({ duration_ms: undefined }), wire({ duration_ms: null })])).toBe(0);
    expect(maxDuration([])).toBe(0);
  });
  it("returns the largest duration_ms across flows", () => {
    expect(
      maxDuration([wire({ duration_ms: 12.5 }), wire({ duration_ms: 40 }), wire({ duration_ms: null })]),
    ).toBe(40);
  });
});
