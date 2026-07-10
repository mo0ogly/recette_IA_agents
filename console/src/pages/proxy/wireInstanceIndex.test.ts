import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import { indexInstances } from "./wireInstanceIndex";

function flow(seq: number, over: object): WireFlow {
  return {
    seq, method: "POST", scheme: "https", host: "api.openai.com", port: 443,
    path: "/v1/x", status_code: 200, ok: true,
    content_type: "application/json",
    request_body: "{}", response_body: "{}",
    run_id: "r1", side_effect_hash: null,
    ...over,
  } as WireFlow;
}

describe("indexInstances", () => {
  it("returns no rows for a capture without instance tags", () => {
    expect(indexInstances([flow(1, {})])).toEqual([]);
  });

  it("rolls flows up per instance with sessions, hosts and failures", () => {
    const flows = [
      flow(1, { instance_id: "triage", session_id: "s1", host: "api.openai.com" }),
      flow(2, { instance_id: "triage", session_id: "s2", host: "api.github.com", status_code: 500, ok: false }),
      flow(3, { instance_id: "notify", session_id: "s1", host: "hooks.slack.com" }),
    ];
    const idx = indexInstances(flows);
    expect(idx).toHaveLength(2);
    // Ordered by first appearance: triage (seq 1) then notify (seq 3).
    expect(idx[0]).toMatchObject({
      instanceId: "triage",
      sessions: 2,
      hosts: ["api.github.com", "api.openai.com"],
      count: 2,
      fails: 1,
      firstSeq: 1,
      lastSeq: 2,
    });
    expect(idx[1]).toMatchObject({ instanceId: "notify", sessions: 1, count: 1, fails: 0 });
  });

  it("is deterministic on the same capture (I4)", () => {
    const flows = [
      flow(2, { instance_id: "b", session_id: "s1" }),
      flow(1, { instance_id: "a", session_id: "s1" }),
    ];
    expect(indexInstances(flows)).toEqual(indexInstances(flows));
    // Ordered by firstSeq regardless of input order: a(1) before b(2).
    expect(indexInstances(flows).map((i) => i.instanceId)).toEqual(["a", "b"]);
  });
});
