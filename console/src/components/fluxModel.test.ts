/**
 * fluxModel tests (R16 contract gate) -- asserted against the real captured
 * audit fixture (auditEvents.fixture.json), not invented payloads. The fixture
 * carries the three governance shapes we decorate: a denied action, an
 * escalated/pending action, and an approval resolution.
 */

import { describe, expect, it } from "vitest";

import auditFixture from "../hooks/__fixtures__/auditEvents.fixture.json";
import type { AuditEvent } from "../types/platform";
import {
  buildStreamModel,
  canonicalLine,
  distinctPayloadValues,
  eventApprovalState,
  eventRisk,
  eventRiskLevel,
  eventVerdict,
  filterEvents,
  isEmptyFilter,
  riskColor,
  streamDecorations,
} from "./fluxModel";

const events = (auditFixture as unknown as { events: AuditEvent[] }).events;

// Fixture anchors (fail loudly if the captured fixture drifts).
const denied = events.find((e) => e.seq === 1)!;
const escalated = events.find((e) => e.seq === 2)!;
const resolved = events.find((e) => e.seq === 3)!;

describe("extractors", () => {
  it("reads the verdict out of the nested policy_decision object", () => {
    expect(eventVerdict(denied)).toBe("deny");
    expect(eventVerdict(escalated)).toBe("escalate");
    // approval_resolved carries no policy_decision -> null, not a crash.
    expect(eventVerdict(resolved)).toBeNull();
  });

  it("reads the approval state", () => {
    expect(eventApprovalState(denied)).toBe("none");
    expect(eventApprovalState(escalated)).toBe("pending");
    expect(eventApprovalState(resolved)).toBe("denied");
  });

  it("reads risk score and level", () => {
    expect(eventRisk(denied)).toBe(3);
    expect(eventRiskLevel(denied)).toBe("high");
    // resolution event has no risk fields.
    expect(eventRisk(resolved)).toBeNull();
    expect(eventRiskLevel(resolved)).toBeNull();
  });
});

describe("filterEvents", () => {
  it("is a pass-through for an empty filter", () => {
    expect(isEmptyFilter({})).toBe(true);
    expect(filterEvents(events, {})).toBe(events);
  });

  it("filters by exact action_type", () => {
    // All three fixture events share action_type=suspend_user.
    const out = filterEvents(events, { actionType: "suspend_user" });
    expect(out.map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(filterEvents(events, { actionType: "no-such" })).toHaveLength(0);
  });

  it("filters by target_system", () => {
    expect(filterEvents(events, { targetSystem: "okta" }).map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(filterEvents(events, { targetSystem: "no-such" })).toHaveLength(0);
  });

  it("drops events below the min risk and those without a score", () => {
    // resolved (seq 3) has no risk_score -> excluded by any minRisk clause.
    expect(filterEvents(events, { minRisk: 3 }).map((e) => e.seq)).toEqual([1, 2]);
    expect(filterEvents(events, { minRisk: 4 })).toHaveLength(0);
  });

  it("combines clauses with AND", () => {
    // action_type matches all three, but minRisk=3 drops seq 3 (no score).
    const out = filterEvents(events, { actionType: "suspend_user", minRisk: 3 });
    expect(out.map((e) => e.seq)).toEqual([1, 2]);
  });
});

describe("distinctPayloadValues", () => {
  it("returns sorted distinct action types", () => {
    expect(distinctPayloadValues(events, "action_type")).toEqual(["suspend_user"]);
  });
  it("returns sorted distinct target systems", () => {
    expect(distinctPayloadValues(events, "target_system")).toEqual(["okta"]);
  });
});

describe("buildStreamModel", () => {
  it("maps one event to one line, 1-based, in order", () => {
    const model = buildStreamModel(events);
    expect(model.text.split("\n")).toHaveLength(events.length);
    expect(model.lines.map((l) => l.line)).toEqual([1, 2, 3]);
    expect(model.lines.map((l) => l.seq)).toEqual([1, 2, 3]);
    // Line text is the canonical serialization (payload preserved).
    expect(model.text.split("\n")[0]).toBe(canonicalLine(events[0]));
  });

  it("carries the governance metadata per line", () => {
    const model = buildStreamModel(events);
    expect(model.lines[0]).toMatchObject({ verdict: "deny", riskLevel: "high" });
    expect(model.lines[1]).toMatchObject({ verdict: "escalate", approvalState: "pending" });
  });
});

describe("riskColor", () => {
  it("maps levels to distinct colours and unknown to undefined", () => {
    expect(riskColor("high")).toBeDefined();
    expect(riskColor("low")).toBeDefined();
    expect(riskColor("high")).not.toBe(riskColor("low"));
    expect(riskColor(null)).toBeUndefined();
    expect(riskColor("weird")).toBeUndefined();
  });
});

describe("streamDecorations", () => {
  it("decorates verdict, approval and risk; skips signal-less lines", () => {
    const { lines } = buildStreamModel(events);
    const decos = streamDecorations(lines);

    const d1 = decos.find((d) => d.line === 1)!;
    expect(d1.className).toBe("flux-verdict-deny");
    expect(d1.minimapColor).toBe(riskColor("high"));
    expect(d1.hover).toContain("verdict: deny");

    const d2 = decos.find((d) => d.line === 2)!;
    expect(d2.className).toBe("flux-verdict-escalate");
    expect(d2.glyphMarginClassName).toBe("flux-appr-pending");

    // seq 3: approval_state "denied" -> still decorated with a glyph.
    const d3 = decos.find((d) => d.line === 3)!;
    expect(d3.glyphMarginClassName).toBe("flux-appr-denied");
  });

  it("emits no decoration for a line with no governance signal", () => {
    const plain: AuditEvent = {
      seq: 99,
      event_id: "evt-plain",
      schema_version: "1",
      kind: "info",
      payload: {},
      prev_hash: "x",
      hash: "y",
    };
    const { lines } = buildStreamModel([plain]);
    expect(streamDecorations(lines)).toHaveLength(0);
  });
});
