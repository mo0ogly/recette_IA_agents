/**
 * Run-status helpers shared by the dashboard and the agents page so both read
 * a run the same way: one status light (voyant) vocabulary, one source of truth.
 */

export interface Voyant {
  label: string;
  cls: string;
}

/** Launch outcome tally over a set of runs (dashboard KPI). */
export interface LaunchTally {
  /** Runs that finished successfully. */
  succeeded: number;
  /** Runs that ended in error. */
  failed: number;
  /** Runs stopped by the operator (neither success nor failure). */
  stopped: number;
}

/** Count terminal launch outcomes over the runs list (ignores pending/running). */
export function launchTally(runs: ReadonlyArray<{ status: string }>): LaunchTally {
  const tally: LaunchTally = { succeeded: 0, failed: 0, stopped: 0 };
  for (const r of runs) {
    if (r.status === "completed") {
      tally.succeeded += 1;
    } else if (r.status === "failed") {
      tally.failed += 1;
    } else if (r.status === "stopped") {
      tally.stopped += 1;
    }
  }
  return tally;
}

/** Run status -> status light (voyant): label + colour class. */
export function voyantFor(status: string): Voyant {
  switch (status) {
    case "running":
      return { label: "demarre", cls: "voyant-run" };
    case "pending":
      return { label: "en attente", cls: "voyant-pending" };
    case "completed":
      return { label: "termine", cls: "voyant-done" };
    case "failed":
      return { label: "erreur", cls: "voyant-error" };
    case "stopped":
      return { label: "arrete", cls: "voyant-stopped" };
    default:
      return { label: "inactif", cls: "voyant-idle" };
  }
}
