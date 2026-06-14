/**
 * fluxModel -- pure, Monaco-free helpers backing the sophisticated analyzer.
 *
 * Everything here is a pure function over AuditEvent[] so it is unit-testable
 * without a DOM or the Monaco runtime (which cannot load under jsdom). The
 * viewer components consume these outputs and translate them into Monaco
 * decorations / diff models. Keeping the semantics here means the colour,
 * filter and heatmap rules are asserted against the real audit fixture rather
 * than eyeballed in the editor.
 *
 * Read-only by construction (I1): these helpers describe how to DISPLAY the
 * immutable audit log, they never mutate an event.
 */

import type { AuditEvent, PolicyVerdict } from "../types/platform";

/** Approval lifecycle states carried by an audited action (canonical model). */
export type ApprovalState = "none" | "pending" | "approved" | "denied" | "timeout";

const VERDICTS: ReadonlySet<string> = new Set(["allow", "deny", "escalate"]);
const APPROVAL_STATES: ReadonlySet<string> = new Set([
  "none",
  "pending",
  "approved",
  "denied",
  "timeout",
]);

/** Extract the policy verdict (allow/deny/escalate) or null when absent. */
export function eventVerdict(e: AuditEvent): PolicyVerdict | null {
  const pd = e.payload?.policy_decision;
  if (pd !== null && typeof pd === "object" && "verdict" in pd) {
    const v = (pd as { verdict?: unknown }).verdict;
    return typeof v === "string" && VERDICTS.has(v) ? (v as PolicyVerdict) : null;
  }
  return null;
}

/** Extract the approval state, or null when the event carries none. */
export function eventApprovalState(e: AuditEvent): ApprovalState | null {
  const a = e.payload?.approval_state;
  return typeof a === "string" && APPROVAL_STATES.has(a) ? (a as ApprovalState) : null;
}

/** Numeric risk score (for the min-risk filter), or null when absent. */
export function eventRisk(e: AuditEvent): number | null {
  const r = e.payload?.risk_score;
  return typeof r === "number" && Number.isFinite(r) ? r : null;
}

/** Categorical risk level (drives the heatmap colour), lowercased or null. */
export function eventRiskLevel(e: AuditEvent): string | null {
  const l = e.payload?.risk_level;
  return typeof l === "string" && l.length > 0 ? l.toLowerCase() : null;
}

/** Filter applied to the stream before serialization (all clauses are AND). */
export interface FluxFilter {
  /** Exact match on payload.action_type. */
  actionType?: string;
  /** Exact match on payload.target_system. */
  targetSystem?: string;
  /** Keep events whose risk_score is >= minRisk (events without a score drop). */
  minRisk?: number;
}

/** True when no clause is set: an empty filter is a no-op pass-through. */
export function isEmptyFilter(f: FluxFilter): boolean {
  return (
    (f.actionType === undefined || f.actionType === "") &&
    (f.targetSystem === undefined || f.targetSystem === "") &&
    f.minRisk === undefined
  );
}

/** Apply the filter, preserving seq order (the stream stays append-ordered). */
export function filterEvents(events: AuditEvent[], f: FluxFilter): AuditEvent[] {
  if (isEmptyFilter(f)) {
    return events;
  }
  return events.filter((e) => {
    if (f.actionType !== undefined && f.actionType !== "") {
      if (e.payload?.action_type !== f.actionType) {
        return false;
      }
    }
    if (f.targetSystem !== undefined && f.targetSystem !== "") {
      if (e.payload?.target_system !== f.targetSystem) {
        return false;
      }
    }
    if (f.minRisk !== undefined) {
      const r = eventRisk(e);
      if (r === null || r < f.minRisk) {
        return false;
      }
    }
    return true;
  });
}

/** Distinct, sorted values of a payload string field (for filter selects). */
export function distinctPayloadValues(
  events: AuditEvent[],
  field: "action_type" | "target_system",
): string[] {
  const seen = new Set<string>();
  for (const e of events) {
    const v = e.payload?.[field];
    if (typeof v === "string" && v.length > 0) {
      seen.add(v);
    }
  }
  return [...seen].sort();
}

/**
 * Stable top-level key order so two serializations of one event are diffable.
 * Reorders the top-level keys only; an array replacer cannot be used because it
 * filters keys recursively and would strip nested objects (e.g. `payload`).
 */
export function canonicalLine(e: AuditEvent): string {
  const source = e as unknown as Record<string, unknown>;
  const ordered: Record<string, unknown> = {};
  for (const key of Object.keys(source).sort()) {
    ordered[key] = source[key];
  }
  return JSON.stringify(ordered);
}

/** Per-line metadata for the JSONL stream (one event == one line). */
export interface FluxLineMeta {
  /** Audit sequence of the event on this line. */
  seq: number;
  /** 1-based line number in the serialized stream. */
  line: number;
  verdict: PolicyVerdict | null;
  approvalState: ApprovalState | null;
  riskScore: number | null;
  riskLevel: string | null;
}

/** Serialized stream plus the per-line metadata that drives decorations. */
export interface FluxStreamModel {
  text: string;
  lines: FluxLineMeta[];
}

/** Build the JSONL stream text and the per-line metadata in one pass. */
export function buildStreamModel(events: AuditEvent[]): FluxStreamModel {
  const lines: FluxLineMeta[] = events.map((e, i) => ({
    seq: e.seq,
    line: i + 1,
    verdict: eventVerdict(e),
    approvalState: eventApprovalState(e),
    riskScore: eventRisk(e),
    riskLevel: eventRiskLevel(e),
  }));
  return { text: events.map(canonicalLine).join("\n"), lines };
}

/** Heatmap colour for a risk level (minimap + glyph). Undefined = no tint. */
export function riskColor(level: string | null): string | undefined {
  switch (level) {
    case "critical":
      return "#e23b3b";
    case "high":
      return "#d64545";
    case "medium":
      return "#d6a13d";
    case "low":
      return "#3d8f5b";
    default:
      return undefined;
  }
}

/**
 * A Monaco-agnostic decoration descriptor. The viewer maps each field onto a
 * monaco.editor.IModelDeltaDecoration; testing this list keeps the colour and
 * heatmap rules verifiable without the editor runtime.
 */
export interface FluxDecoration {
  /** 1-based line the decoration applies to (whole line). */
  line: number;
  /** Whole-line background class keyed on the verdict. */
  className?: string;
  /** Gutter glyph class keyed on the approval state. */
  glyphMarginClassName?: string;
  /** Minimap tint (risk heatmap); undefined leaves the line untinted. */
  minimapColor?: string;
  /** Hover text summarising the governance outcome of the line. */
  hover: string;
}

/** Build decorations (verdict colour + approval glyph + risk heatmap). */
export function streamDecorations(lines: FluxLineMeta[]): FluxDecoration[] {
  const out: FluxDecoration[] = [];
  for (const m of lines) {
    const hasApproval = m.approvalState !== null && m.approvalState !== "none";
    const color = riskColor(m.riskLevel);
    // A line with no governance signal at all gets no decoration (keeps the
    // gutter clean for plain informational events).
    if (m.verdict === null && !hasApproval && color === undefined) {
      continue;
    }
    const hoverParts: string[] = [`seq ${m.seq}`];
    if (m.verdict !== null) {
      hoverParts.push(`verdict: ${m.verdict}`);
    }
    if (hasApproval) {
      hoverParts.push(`approval: ${m.approvalState}`);
    }
    if (m.riskLevel !== null) {
      hoverParts.push(`risk: ${m.riskLevel}`);
    }
    out.push({
      line: m.line,
      className: m.verdict !== null ? `flux-verdict-${m.verdict}` : undefined,
      glyphMarginClassName: hasApproval ? `flux-appr-${m.approvalState}` : undefined,
      minimapColor: color,
      hover: hoverParts.join(" | "),
    });
  }
  return out;
}
