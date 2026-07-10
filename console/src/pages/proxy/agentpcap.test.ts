import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import { chainDigests, fromAgentPcap, toAgentPcap } from "./agentpcap";

function flow(over: Partial<WireFlow> & object): WireFlow {
  return {
    seq: 1, method: "POST", scheme: "https", host: "api.openai.com", port: 443,
    path: "/v1/chat/completions", status_code: 200, ok: true,
    content_type: "application/json",
    request_body: '{"model":"gpt-4o"}', response_body: "{}",
    run_id: "r1", side_effect_hash: null,
    ...over,
  } as WireFlow;
}

const FLOWS = [flow({ seq: 1 }), flow({ seq: 2, status_code: 403, ok: false })];

describe("agentpcap round-trip", () => {
  it("exports then re-imports the same flows, verified", () => {
    const text = toAgentPcap(FLOWS);
    const back = fromAgentPcap(text);
    expect(back.error).toBeNull();
    expect(back.verified).toBe(true);
    expect(back.flows).toEqual(FLOWS);
  });

  it("is byte-identical on the same input (I4)", () => {
    expect(toAgentPcap(FLOWS)).toBe(toAgentPcap(FLOWS));
  });

  it("an empty capture round-trips", () => {
    const back = fromAgentPcap(toAgentPcap([]));
    expect(back).toEqual({ flows: [], verified: true, error: null });
  });
});

describe("agentpcap tamper evidence", () => {
  it("detects an edited flow body", () => {
    const file = JSON.parse(toAgentPcap(FLOWS));
    file.flows[0].request_body = '{"model":"tampered"}';
    const back = fromAgentPcap(JSON.stringify(file));
    expect(back.verified).toBe(false);
    expect(back.error).toContain("integrite");
  });

  it("detects reordered flows", () => {
    const file = JSON.parse(toAgentPcap(FLOWS));
    file.flows.reverse();
    expect(fromAgentPcap(JSON.stringify(file)).verified).toBe(false);
  });

  it("detects a dropped flow", () => {
    const file = JSON.parse(toAgentPcap(FLOWS));
    file.flows.pop();
    expect(fromAgentPcap(JSON.stringify(file)).verified).toBe(false);
  });

  it("chains depend on order and content", () => {
    const a = chainDigests(FLOWS);
    const b = chainDigests([...FLOWS].reverse());
    expect(a).not.toEqual(b);
    expect(a).toHaveLength(2);
  });
});

describe("agentpcap malformed input", () => {
  it("invalid JSON is an explicit error, never a throw", () => {
    const back = fromAgentPcap("not json {");
    expect(back.flows).toEqual([]);
    expect(back.error).toContain("JSON");
  });

  it("a foreign JSON file is rejected by format", () => {
    expect(fromAgentPcap('{"hello":"world"}').error).toContain("format");
  });

  it("an unsupported version is rejected explicitly", () => {
    const file = JSON.parse(toAgentPcap(FLOWS));
    file.version = 99;
    expect(fromAgentPcap(JSON.stringify(file)).error).toContain("version");
  });
});
