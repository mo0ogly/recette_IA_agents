import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import { computeWireStats } from "./wireStats";

const LAYERS = {
  l3l4: { src_ip: "10.0.0.9", dst_ip: "1.2.3.4", src_port: 51000, dst_port: 443, transport: "tcp", ip_version: 4 },
  tls: { version: "TLS 1.3", cipher: null, sni: "api.openai.com", alpn: "h2", ja3: "aaa", ja3_string: null },
  http: { version: "HTTP/2", reason: "OK", request_headers: {}, response_headers: {} },
  timing: { tcp_setup_ms: 10, tls_setup_ms: 20, ttfb_ms: 100, total_ms: 130 },
};

function llmResp(prompt: number, completion: number): string {
  return JSON.stringify({
    choices: [{ message: { content: "ok" }, finish_reason: "stop" }],
    usage: { prompt_tokens: prompt, completion_tokens: completion },
  });
}

function flow(over: Partial<WireFlow> & object): WireFlow {
  return {
    seq: 1, method: "POST", scheme: "https", host: "api.openai.com", port: 443,
    path: "/v1/chat/completions", status_code: 200, ok: true,
    content_type: "application/json",
    request_body: JSON.stringify({ model: "gpt-4o-mini", messages: [] }),
    response_body: "{}", run_id: "r1", side_effect_hash: null,
    ...over,
  } as WireFlow;
}

const FLOWS: WireFlow[] = [
  flow({ seq: 1, response_body: llmResp(100, 20), ...({ instance_id: "a", layers: LAYERS } as object) }),
  flow({ seq: 2, response_body: llmResp(50, 10), ...({ instance_id: "a", layers: LAYERS } as object) }),
  // A non-LLM failure on another host, empty bodies -> no l8, counts as a failure.
  flow({
    seq: 3, host: "health.example.com", path: "/health", status_code: 500, ok: false,
    request_body: "{}", response_body: "{}",
  }),
];

describe("computeWireStats", () => {
  it("returns an empty stat set for no flows", () => {
    const s = computeWireStats([]);
    expect(s.totalFlows).toBe(0);
    expect(s.protocols).toEqual([]);
  });

  it("counts totals and failures", () => {
    const s = computeWireStats(FLOWS);
    expect(s.totalFlows).toBe(3);
    expect(s.fails).toBe(1);
  });

  it("protocol hierarchy = share of flows carrying each layer", () => {
    const s = computeWireStats(FLOWS);
    const l8 = s.protocols.find((p) => p.layer === "l8");
    const tls = s.protocols.find((p) => p.layer === "tls");
    expect(l8?.flows).toBe(2); // flows 1 & 2 decode as LLM
    expect(tls?.flows).toBe(2);
    expect(l8?.share).toBeCloseTo(2 / 3);
  });

  it("endpoint hierarchy sorted by flow count", () => {
    const s = computeWireStats(FLOWS);
    expect(s.endpoints[0]).toMatchObject({ host: "api.openai.com", flows: 2, fails: 0 });
    expect(s.endpoints[1]).toMatchObject({ host: "health.example.com", flows: 1, fails: 1 });
  });

  it("token accounting rolled up per instance", () => {
    const s = computeWireStats(FLOWS);
    expect(s.tokensTotal).toEqual({ input: 150, output: 30 });
    expect(s.tokensByInstance).toHaveLength(1);
    expect(s.tokensByInstance[0]).toMatchObject({
      instance: "a", model: "gpt-4o-mini", flows: 2, input: 150, output: 30,
    });
  });
});
