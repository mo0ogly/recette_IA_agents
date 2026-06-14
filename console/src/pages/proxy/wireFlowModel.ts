/**
 * wireFlowModel -- pure helpers for the wire-overlay panel.
 *
 * Pure functions over WireFlow[] so they are unit-testable without a DOM. The
 * panel consumes these outputs (a console line, a pretty JSON of the selected
 * flow). Read-only by construction (I1/I5): a wire flow is a view over bytes
 * that already crossed the wire; nothing here mutates one.
 */

import type { WireFlow } from "../../types/platform";

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
