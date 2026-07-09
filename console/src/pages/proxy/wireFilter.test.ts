import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import { applyWireFilter, compileWireFilter } from "./wireFilter";

function flow(over: Partial<WireFlow> & object): WireFlow {
  return {
    seq: 1, method: "POST", scheme: "https", host: "api.example.com", port: 443,
    path: "/v1/chat/completions", status_code: 200, ok: true,
    content_type: "application/json", request_body: "{}", response_body: "{}",
    run_id: "r1", side_effect_hash: null,
    ...over,
  } as WireFlow;
}

// Two flows with layers + tracking identity to exercise the field registry.
const A = flow({
  seq: 1, host: "api.openai.com", status_code: 200,
  ...({
    session_id: "s1", instance_id: "attacker",
    layers: {
      l3l4: { src_ip: "10.0.0.9", dst_ip: "1.2.3.4", src_port: 51000, dst_port: 443, transport: "tcp", ip_version: 4 },
      tls: { version: "TLS 1.3", cipher: null, sni: "api.openai.com", alpn: "h2", ja3: "aaa111", ja3_string: null },
      http: { version: "HTTP/2", reason: "OK", request_headers: {}, response_headers: {} },
      timing: { tcp_setup_ms: 12, tls_setup_ms: 30, ttfb_ms: 210, total_ms: 240 },
    },
  } as object),
});

const B = flow({
  seq: 2, host: "api.anthropic.com", status_code: 500, method: "GET",
  ...({
    session_id: "s2", instance_id: "auditor",
    layers: {
      l3l4: { src_ip: "10.0.0.9", dst_ip: "9.9.9.9", src_port: 51001, dst_port: 443, transport: "tcp", ip_version: 4 },
      tls: { version: "TLS 1.2", cipher: null, sni: "api.anthropic.com", alpn: "http/1.1", ja3: "bbb222", ja3_string: null },
      timing: { tcp_setup_ms: 20, tls_setup_ms: 60, ttfb_ms: 900, total_ms: 950 },
    },
  } as object),
});

const FLOWS = [A, B];

describe("compileWireFilter — parsing", () => {
  it("empty filter passes everything", () => {
    expect(applyWireFilter(FLOWS, "").length).toBe(2);
    expect(compileWireFilter("").ok).toBe(true);
  });
  it("reports an unknown field", () => {
    const r = compileWireFilter("nope.bad == 1");
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/unknown field/);
  });
  it("a parse error yields a pass-through predicate (list stays usable)", () => {
    const r = compileWireFilter("host ==");
    expect(r.ok).toBe(false);
    expect(FLOWS.filter(r.predicate).length).toBe(2);
  });
});

describe("comparisons over dissected fields", () => {
  it("string equality + inequality (case-insensitive)", () => {
    expect(applyWireFilter(FLOWS, 'host == "api.openai.com"').map((f) => f.seq)).toEqual([1]);
    expect(applyWireFilter(FLOWS, 'host != "api.openai.com"').map((f) => f.seq)).toEqual([2]);
    expect(applyWireFilter(FLOWS, "method == get").map((f) => f.seq)).toEqual([2]);
  });
  it("numeric comparisons on status + timing", () => {
    expect(applyWireFilter(FLOWS, "status >= 400").map((f) => f.seq)).toEqual([2]);
    expect(applyWireFilter(FLOWS, "timing.ttfb_ms > 500").map((f) => f.seq)).toEqual([2]);
    expect(applyWireFilter(FLOWS, "l3l4.dst_port == 443").length).toBe(2);
  });
  it("contains + regex", () => {
    expect(applyWireFilter(FLOWS, 'host contains "openai"').map((f) => f.seq)).toEqual([1]);
    expect(applyWireFilter(FLOWS, "tls.ja3 ~ ^bbb").map((f) => f.seq)).toEqual([2]);
  });
  it("tracking identity fields", () => {
    expect(applyWireFilter(FLOWS, "instance == attacker").map((f) => f.seq)).toEqual([1]);
    expect(applyWireFilter(FLOWS, "session == s2").map((f) => f.seq)).toEqual([2]);
  });
});

describe("boolean composition", () => {
  it("&& / || / ! / parentheses", () => {
    expect(applyWireFilter(FLOWS, "status >= 400 && method == get").map((f) => f.seq)).toEqual([2]);
    expect(
      applyWireFilter(FLOWS, 'host contains "openai" || status >= 400').map((f) => f.seq),
    ).toEqual([1, 2]);
    expect(applyWireFilter(FLOWS, "!(status >= 400)").map((f) => f.seq)).toEqual([1]);
  });
  it("bare field = presence", () => {
    // Both carry tls; only A's http layer is present.
    expect(applyWireFilter(FLOWS, "tls.ja3").length).toBe(2);
    expect(applyWireFilter(FLOWS, "http.reason").map((f) => f.seq)).toEqual([1]);
  });
});
