/**
 * wireFlowModel -- pure helpers for the wire-overlay panel.
 *
 * Pure functions over WireFlow[] so they are unit-testable without a DOM. The
 * panel consumes these outputs (a console line, a pretty JSON of the selected
 * flow). Read-only by construction (I1/I5): a wire flow is a view over bytes
 * that already crossed the wire; nothing here mutates one.
 */

import type { WireFlow } from "../../types/platform";
import { instanceId, sessionId } from "./wireLayers";

/** A single wire flow summarised as one console line. */
export interface WireFlowLine {
  seq: number;
  /** "ok" when the exchange completed with a <400 status, else "fail". */
  outcome: "ok" | "fail";
  label: string;
}

/** One-line summary: method, host/path, status code. */
export function wireFlowToLine(f: WireFlow): WireFlowLine {
  return {
    seq: f.seq,
    outcome: f.ok ? "ok" : "fail",
    label: `${f.method} ${f.host}${f.path} -> ${f.status_code}`,
  };
}

/** Pretty JSON for one flow selected by seq, or a hint when none is selected. */
export function wireFlowJson(flows: WireFlow[], seq: number | null): string {
  if (seq === null) {
    return "// select a flow on the left to inspect it";
  }
  const found = flows.find((f) => f.seq === seq);
  return found === undefined
    ? "// no such flow (it may have aged out of the bounded buffer)"
    : JSON.stringify(found, null, 2);
}

/** Count of failed flows (drives the header summary). */
export function wireFailureCount(flows: WireFlow[]): number {
  return flows.reduce((n, f) => (f.ok ? n : n + 1), 0);
}

/** Largest duration_ms across the given flows (0 when none carries one).
 *  Drives the waterfall bar scale; pure (no clock, no I/O). duration_ms is OPS
 *  metadata on the view only, never a judge/decision/replay input (I4). */
export function maxDuration(flows: WireFlow[]): number {
  return flows.reduce((m, f) => Math.max(m, f.duration_ms ?? 0), 0);
}

/** Filter over wire flows (all clauses AND; empty = pass-through). */
export interface WireFlowFilter {
  host?: string;
  method?: string;
  status?: string; // string for select binding; compared to String(status_code)
  runId?: string;
  /** Session (one conversation/episode) exact match. */
  sessionId?: string;
  /** Autonomous agent instance exact match -- follows one instance across sessions. */
  instanceId?: string;
  /** Wireshark-style display filter over dissected fields (see wireFilter.ts).
   *  Client-side only (does not affect the server fetch), so it is intentionally
   *  NOT part of isEmptyWireFilter. */
  df?: string;
  /** Free text, matched case-insensitively in path + request_body + response_body. */
  text?: string;
}

export function isEmptyWireFilter(f: WireFlowFilter): boolean {
  return (
    !f.host && !f.method && !f.status && !f.runId && !f.sessionId && !f.instanceId && !f.text
  );
}

export function filterWireFlows(flows: WireFlow[], f: WireFlowFilter): WireFlow[] {
  if (isEmptyWireFilter(f)) {
    return flows;
  }
  const needle = f.text?.toLowerCase();
  return flows.filter((flow) => {
    if (f.host && flow.host !== f.host) return false;
    if (f.method && flow.method !== f.method) return false;
    if (f.status && String(flow.status_code) !== f.status) return false;
    if (f.runId && flow.run_id !== f.runId) return false;
    if (f.sessionId && sessionId(flow) !== f.sessionId) return false;
    if (f.instanceId && instanceId(flow) !== f.instanceId) return false;
    if (needle) {
      const hay = `${flow.path}\n${flow.request_body}\n${flow.response_body}`.toLowerCase();
      if (!hay.includes(needle)) return false;
    }
    return true;
  });
}

/** Distinct values of a flow field, sorted, for select options. */
export function distinctWireValues(
  flows: WireFlow[],
  key: "host" | "method" | "run_id",
): string[] {
  const set = new Set<string>();
  for (const flow of flows) {
    const v = key === "run_id" ? flow.run_id : flow[key];
    if (v) set.add(String(v));
  }
  return [...set].sort();
}
