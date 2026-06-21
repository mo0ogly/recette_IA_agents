import { describe, expect, it } from "vitest";

import type { WireFlow } from "../../types/platform";
import { flowsToHar, toJsonl } from "./proxyExport";

function wire(over: Partial<WireFlow>): WireFlow {
  return {
    seq: 1, method: "POST", scheme: "http", host: "127.0.0.1", port: 9101,
    path: "/github/execute", status_code: 200, ok: true,
    content_type: "application/json", request_body: '{"a":1}', response_body: '{"b":2}',
    run_id: "r1", side_effect_hash: "H1", ...over,
  };
}

describe("toJsonl", () => {
  it("serialises one object per line", () => {
    expect(toJsonl([{ a: 1 }, { b: 2 }]).split("\n")).toEqual(['{"a":1}', '{"b":2}']);
  });
  it("returns empty string for no items", () => {
    expect(toJsonl([])).toBe("");
  });
});

describe("flowsToHar", () => {
  it("builds a structurally valid HAR 1.2 document", () => {
    const har = JSON.parse(flowsToHar([wire({ path: "/p", status_code: 201 })]));
    expect(har.log.version).toBe("1.2");
    expect(har.log.entries).toHaveLength(1);
    const e = har.log.entries[0];
    expect(e.request.method).toBe("POST");
    expect(e.request.url).toContain("/p");
    expect(e.response.status).toBe(201);
    expect(e.response.content.text).toBe('{"b":2}');
  });
});
