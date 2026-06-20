/**
 * Pure view helpers for the Discovery x Exchange page (no I/O, unit-testable).
 *
 * Maps the backend ExchangeReport shapes onto display rows/badges. Kept separate
 * from the component so the verdict mapping (identified vs ghost, detected vs
 * ghost agent) is asserted directly.
 */

import type { ExchangeAgentDetection, ExchangeVerdict } from "../../types/platform";

export interface ExchangeLine {
  seq: number;
  kind: "hook" | "wire";
  /** "identifie" for an identified exchange, "ghost" otherwise. */
  outcome: "identifie" | "ghost";
  /** Human one-liner: the real target + (for ghost) the reconcile reason. */
  label: string;
}

/** Map one exchange verdict to a display line (pure). */
export function exchangeToLine(e: ExchangeVerdict): ExchangeLine {
  const base = e.action_type ? `${e.action_type} ${e.target}` : e.target;
  const label = e.identified ? base : `${base} (${e.reason ?? "ghost"})`;
  return {
    seq: e.seq,
    kind: e.kind,
    outcome: e.identified ? "identifie" : "ghost",
    label,
  };
}

/** An agent is GHOST when discovery saw it on no surface, DETECTE otherwise. */
export function agentOutcome(a: ExchangeAgentDetection): "DETECTE" | "GHOST" {
  return a.detected_anywhere ? "DETECTE" : "GHOST";
}

/** Surfaces an agent was detected on, in display order (pure). */
export function detectedSurfaces(a: ExchangeAgentDetection): string[] {
  return a.per_surface.filter((s) => s.detected).map((s) => s.surface);
}

/** Distinct originating run ids across the exchanges, sorted (pure). */
export function distinctRuns(exchanges: ExchangeVerdict[]): string[] {
  const runs = new Set<string>();
  for (const e of exchanges) {
    if (e.run_id) runs.add(e.run_id);
  }
  return Array.from(runs).sort();
}

/** Keep the exchanges of one run; the empty filter keeps all (pure). */
export function filterByRun(exchanges: ExchangeVerdict[], runId: string): ExchangeVerdict[] {
  return runId ? exchanges.filter((e) => e.run_id === runId) : exchanges;
}

/** Agents that appear in a HOOK exchange of the selected run (pure). The empty
 *  filter keeps every agent. Wire-only flows carry no agent_id, so an agent is
 *  attributed to a run only through its hook exchanges. */
export function agentsForRun(
  agents: ExchangeAgentDetection[],
  exchanges: ExchangeVerdict[],
  runId: string,
): ExchangeAgentDetection[] {
  if (!runId) return agents;
  const inRun = new Set(
    exchanges.filter((e) => e.kind === "hook" && e.run_id === runId).map((e) => e.agent_id),
  );
  return agents.filter((a) => inRun.has(a.agent_id));
}

/** Ghost-exchange count over a list (wire-only, not identified) (pure). */
export function ghostCount(exchanges: ExchangeVerdict[]): number {
  return exchanges.filter((e) => !e.identified).length;
}
