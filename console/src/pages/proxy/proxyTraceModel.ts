/**
 * proxyTraceModel -- pure, Monaco-free helpers for the proxy trace console.
 *
 * Everything here is a pure function over ProxyTrace[] so it is unit-testable
 * without a DOM or the Monaco runtime. The page consumes these outputs and
 * renders them (a list line, the JSONL stream, the selected trace JSON).
 *
 * Read-only by construction (I1/I5): traces describe side effects that already
 * happened; these helpers never mutate a trace.
 */

import type { ProxyTrace } from "../../types/platform";

/** A single trace summarised as one console line (list rendering). */
export interface TraceLine {
  seq: number;
  /** "ok" when the side effect succeeded, else "fail" (drives the badge). */
  outcome: "ok" | "fail";
  label: string;
}

/** One-line summary: seq, outcome, action on target, status code. */
export function traceToLine(t: ProxyTrace): TraceLine {
  return {
    seq: t.seq,
    outcome: t.ok ? "ok" : "fail",
    label: `${t.action_type} ${t.target_system}/${t.resource} -> ${t.status_code}`,
  };
}

/** Pretty JSON for one trace selected by seq, or a hint when none is selected. */
export function traceJson(traces: ProxyTrace[], seq: number | null): string {
  if (seq === null) {
    return "// select a trace on the left to inspect it";
  }
  const found = traces.find((t) => t.seq === seq);
  return found === undefined
    ? "// no such trace (it may have aged out of the bounded buffer)"
    : JSON.stringify(found, null, 2);
}

/** Whole buffer as one JSONL document (one trace per line), oldest first. */
export function tracesToJsonl(traces: ProxyTrace[]): string {
  return traces.map((t) => JSON.stringify(t)).join("\n");
}

/** Count of failed traces (drives the header summary). */
export function failureCount(traces: ProxyTrace[]): number {
  return traces.reduce((n, t) => (t.ok ? n : n + 1), 0);
}

/** Filter applied to the trace list (all clauses are AND; empty = pass-through). */
export interface ProxyTraceFilter {
  /** Exact match on agent_id. */
  agentId?: string;
  /** Exact match on target_system. */
  targetSystem?: string;
  /** Exact match on run_id (F3 run <-> traces link). */
  runId?: string;
}

/** True when no clause is set: an empty filter is a no-op. */
export function isEmptyFilter(f: ProxyTraceFilter): boolean {
  return (
    (f.agentId === undefined || f.agentId === "") &&
    (f.targetSystem === undefined || f.targetSystem === "") &&
    (f.runId === undefined || f.runId === "")
  );
}

/** Apply the filter, preserving seq order (the ring stays seq-ordered). */
export function filterTraces(traces: ProxyTrace[], f: ProxyTraceFilter): ProxyTrace[] {
  if (isEmptyFilter(f)) {
    return traces;
  }
  return traces.filter((t) => {
    if (f.agentId !== undefined && f.agentId !== "" && t.agent_id !== f.agentId) {
      return false;
    }
    if (
      f.targetSystem !== undefined &&
      f.targetSystem !== "" &&
      t.target_system !== f.targetSystem
    ) {
      return false;
    }
    if (f.runId !== undefined && f.runId !== "" && t.run_id !== f.runId) {
      return false;
    }
    return true;
  });
}

/** Distinct, sorted values of a trace string field (for the filter selects). */
export function distinctValues(
  traces: ProxyTrace[],
  field: "agent_id" | "target_system" | "run_id",
): string[] {
  const seen = new Set<string>();
  for (const t of traces) {
    const v = t[field];
    if (typeof v === "string" && v.length > 0) {
      seen.add(v);
    }
  }
  return [...seen].sort();
}
