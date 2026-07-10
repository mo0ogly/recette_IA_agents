import { describe, expect, it } from "vitest";
import type { WireFlow } from "../../types/platform";
import {
  compileColorRules,
  parseColorRules,
  serializeColorRules,
} from "./wireColorRules";

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

describe("parseColorRules / serializeColorRules", () => {
  it("round-trips a two-rule string", () => {
    const src = 'red:status >= 500;amber:host == "api.openai.com"';
    const { rules, errors } = parseColorRules(src);
    expect(errors).toEqual([]);
    expect(rules).toEqual([
      { tint: "red", filter: "status >= 500" },
      { tint: "amber", filter: 'host == "api.openai.com"' },
    ]);
    expect(serializeColorRules(rules)).toBe(src);
  });

  it("keeps a semicolon inside a quoted string", () => {
    const { rules, errors } = parseColorRules('green:path == "/a;b"');
    expect(errors).toEqual([]);
    expect(rules).toEqual([{ tint: "green", filter: 'path == "/a;b"' }]);
  });

  it("rejects an unknown tint and a separator-less entry, keeps the rest", () => {
    const { rules, errors } = parseColorRules("purple:status >= 500;nonsense;red:status >= 400");
    expect(rules).toEqual([{ tint: "red", filter: "status >= 400" }]);
    expect(errors).toHaveLength(2);
  });

  it("parses an empty string to no rules, no errors", () => {
    expect(parseColorRules("")).toEqual({ rules: [], errors: [] });
  });
});

describe("compileColorRules", () => {
  it("colors by the FIRST matching rule (Wireshark semantics)", () => {
    const c = compileColorRules('amber:status >= 400;red:status >= 500');
    // 502 matches BOTH rules; the first (amber) wins.
    expect(c.tintFor(flow({ status_code: 502, ok: false }))).toBe("amber");
    expect(c.tintFor(flow({ status_code: 404, ok: false }))).toBe("amber");
    expect(c.tintFor(flow({ status_code: 200 }))).toBeNull();
  });

  it("a rule with an invalid filter is an error and never matches", () => {
    const c = compileColorRules("red:status >=;green:method == \"POST\"");
    expect(c.errors.length).toBeGreaterThan(0);
    // The broken red rule must not swallow everything; the green one works.
    expect(c.tintFor(flow({}))).toBe("green");
  });

  it("is deterministic on the same input (I4)", () => {
    const src = 'red:status >= 500;green:method == "POST"';
    const flows = [flow({ seq: 1 }), flow({ seq: 2, status_code: 503, ok: false })];
    const a = flows.map((f) => compileColorRules(src).tintFor(f));
    const b = flows.map((f) => compileColorRules(src).tintFor(f));
    expect(a).toEqual(b);
    expect(a).toEqual(["green", "red"]);
  });
});
