import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import { wireFlowToCurl } from "./curl";

function wire(over: Partial<WireFlow>): WireFlow {
  return { seq:1, method:"POST", scheme:"http", host:"127.0.0.1", port:9101,
    path:"/github/execute", status_code:200, ok:true, content_type:"application/json",
    request_body:'{"a":1}', response_body:"", run_id:"r1", side_effect_hash:null, ...over };
}

describe("wireFlowToCurl", () => {
  it("builds a curl with method, url, content-type, body", () => {
    const c = wireFlowToCurl(wire({}));
    expect(c).toContain("curl -X POST");
    expect(c).toContain("http://127.0.0.1:9101/github/execute");
    expect(c).toContain("-H 'Content-Type: application/json'");
    expect(c).toContain(`--data '{"a":1}'`);
  });
  it("omits --data when request_body is empty", () => {
    expect(wireFlowToCurl(wire({ method:"GET", request_body:"" }))).not.toContain("--data");
  });
  it("single-quote-escapes a body with a quote", () => {
    expect(wireFlowToCurl(wire({ request_body: "a'b" }))).toContain(`'a'\\''b'`);
  });
});
