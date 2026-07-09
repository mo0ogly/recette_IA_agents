import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import { computeExpertInfo, expertSummary } from "./wireExpert";

function tlsLayer(ja3: string, version: string): object {
  return {
    layers: {
      tls: { version, cipher: null, sni: "api.openai.com", alpn: "h2", ja3, ja3_string: null },
    },
  };
}

function flow(over: Partial<WireFlow> & object): WireFlow {
  return {
    seq: 1, method: "POST", scheme: "https", host: "api.openai.com", port: 443,
    path: "/v1/chat/completions", status_code: 200, ok: true,
    content_type: "application/json",
    request_body: "{}", response_body: "{}",
    run_id: "r1", side_effect_hash: null,
    ...over,
  } as WireFlow;
}

describe("computeExpertInfo", () => {
  it("returns no signal on an empty capture", () => {
    expect(computeExpertInfo([])).toEqual([]);
  });

  it("returns no signal on a clean masked capture", () => {
    // The redaction contract masks secrets as "***" at the source: a masked
    // body must NOT trip the secret scanner (zero false-positive baseline).
    const flows = [
      flow({ seq: 1, request_body: JSON.stringify({ api_key: "***" }) }),
      flow({ seq: 2, response_body: JSON.stringify({ token: "***" }) }),
    ];
    expect(computeExpertInfo(flows)).toEqual([]);
  });

  it("flags an unmasked OpenAI-shaped key in a request body", () => {
    const flows = [
      flow({ seq: 3, request_body: JSON.stringify({ key: "sk-abcdefghijklmnopqrstuvwx" }) }),
    ];
    const signals = computeExpertInfo(flows);
    expect(signals).toHaveLength(1);
    expect(signals[0]).toMatchObject({ seq: 3, severity: "warn", kind: "secret_in_clear" });
    expect(signals[0].message).toContain("OpenAI");
  });

  it("flags an unmasked Anthropic-shaped key in a response body", () => {
    const flows = [
      flow({ seq: 4, response_body: JSON.stringify({ key: "sk-ant-api03-abcdefghijklmnop-qrstu" }) }),
    ];
    const signals = computeExpertInfo(flows);
    expect(signals).toHaveLength(1);
    expect(signals[0].message).toContain("Anthropic");
  });

  it("emits one secret signal per flow, not per pattern hit", () => {
    const body = JSON.stringify({ a: "sk-abcdefghijklmnopqrstuvwx", b: "AKIAABCDEFGHIJKLMNOP" });
    const signals = computeExpertInfo([flow({ seq: 5, request_body: body })]);
    expect(signals.filter((s) => s.kind === "secret_in_clear")).toHaveLength(1);
  });

  it("notes a JA3 drift within one instance and anchors it on the changing flow", () => {
    const flows = [
      flow({ seq: 1, ...({ instance_id: "triage", ...tlsLayer("aaa111", "TLS 1.3") } as object) }),
      flow({ seq: 2, ...({ instance_id: "triage", ...tlsLayer("bbb222", "TLS 1.3") } as object) }),
    ];
    const signals = computeExpertInfo(flows);
    expect(signals).toHaveLength(1);
    expect(signals[0]).toMatchObject({ seq: 2, severity: "note", kind: "ja3_drift" });
    expect(signals[0].message).toContain("triage");
  });

  it("does not report JA3 drift across two DIFFERENT instances", () => {
    const flows = [
      flow({ seq: 1, ...({ instance_id: "a", ...tlsLayer("aaa111", "TLS 1.3") } as object) }),
      flow({ seq: 2, ...({ instance_id: "b", ...tlsLayer("bbb222", "TLS 1.3") } as object) }),
    ];
    expect(computeExpertInfo(flows)).toEqual([]);
  });

  it("notes a TLS downgrade for the same instance (1.3 then 1.2)", () => {
    const flows = [
      flow({ seq: 1, ...({ instance_id: "a", ...tlsLayer("aaa111", "TLS 1.3") } as object) }),
      flow({ seq: 2, ...({ instance_id: "a", ...tlsLayer("aaa111", "TLS 1.2") } as object) }),
    ];
    const signals = computeExpertInfo(flows);
    expect(signals).toHaveLength(1);
    expect(signals[0]).toMatchObject({ seq: 2, severity: "note", kind: "tls_downgrade" });
    expect(signals[0].message).toContain("TLS 1.2");
  });

  it("does not flag an upgrade (1.2 then 1.3) as a downgrade", () => {
    const flows = [
      flow({ seq: 1, ...({ instance_id: "a", ...tlsLayer("aaa111", "TLS 1.2") } as object) }),
      flow({ seq: 2, ...({ instance_id: "a", ...tlsLayer("aaa111", "TLS 1.3") } as object) }),
    ];
    expect(computeExpertInfo(flows)).toEqual([]);
  });

  it("warns on a server error and names the session when tracked", () => {
    const flows = [
      flow({ seq: 6, status_code: 502, ok: false, ...({ session_id: "s-42" } as object) }),
    ];
    const signals = computeExpertInfo(flows);
    expect(signals).toHaveLength(1);
    expect(signals[0]).toMatchObject({ seq: 6, severity: "warn", kind: "server_error" });
    expect(signals[0].message).toContain("502");
    expect(signals[0].message).toContain("s-42");
  });

  it("orders signals most-severe first, then by seq (deterministic, I4)", () => {
    const flows = [
      // seq 1: note (ja3 drift arrives on seq 2 actually) -- build a mix:
      flow({ seq: 1, ...({ instance_id: "a", ...tlsLayer("aaa111", "TLS 1.3") } as object) }),
      flow({ seq: 2, ...({ instance_id: "a", ...tlsLayer("bbb222", "TLS 1.3") } as object) }),
      flow({ seq: 3, status_code: 500, ok: false }),
      flow({ seq: 4, request_body: JSON.stringify({ k: "sk-abcdefghijklmnopqrstuvwx" }) }),
    ];
    const a = computeExpertInfo(flows);
    const b = computeExpertInfo(flows);
    expect(a).toEqual(b); // byte-stable on the same capture
    expect(a.map((s) => `${s.severity}:${s.seq}`)).toEqual([
      "warn:3", // server_error
      "warn:4", // secret_in_clear
      "note:2", // ja3_drift
    ]);
  });
});

describe("expertSummary", () => {
  it("counts signals per severity for the header badge", () => {
    const flows = [
      flow({ seq: 1, status_code: 503, ok: false }),
      flow({ seq: 2, ...({ instance_id: "a", ...tlsLayer("aaa111", "TLS 1.3") } as object) }),
      flow({ seq: 3, ...({ instance_id: "a", ...tlsLayer("bbb222", "TLS 1.3") } as object) }),
    ];
    const summary = expertSummary(computeExpertInfo(flows));
    expect(summary).toEqual({ note: 1, warn: 1, error: 0 });
  });
});
