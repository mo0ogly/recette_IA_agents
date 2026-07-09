import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import { summarizeSessions } from "./wireSessionSummary";

function wire(over: Partial<WireFlow> & object): WireFlow {
  return {
    seq: 1, method: "POST", scheme: "https", host: "api.example.com", port: 443,
    path: "/v1/x", status_code: 200, ok: true, content_type: "application/json",
    request_body: "{}", response_body: "{}", run_id: "r1", side_effect_hash: null,
    ...over,
  } as WireFlow;
}

describe("summarizeSessions", () => {
  it("groups an instance's flows by session, ordered by first appearance", () => {
    const flows = [
      wire({ seq: 1, ...({ session_id: "s1" } as object) }),
      wire({ seq: 2, ...({ session_id: "s2" } as object) }),
      wire({ seq: 3, ok: false, status_code: 500, ...({ session_id: "s1" } as object) }),
    ];
    const out = summarizeSessions(flows);
    expect(out.map((s) => s.sessionId)).toEqual(["s1", "s2"]);
    expect(out[0]).toMatchObject({ sessionId: "s1", count: 2, fails: 1, firstSeq: 1, lastSeq: 3 });
    expect(out[1]).toMatchObject({ sessionId: "s2", count: 1, fails: 0 });
  });

  it("ignores flows without a session_id", () => {
    expect(summarizeSessions([wire({ seq: 1 })])).toEqual([]);
  });
});
