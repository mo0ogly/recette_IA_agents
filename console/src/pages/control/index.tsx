/**
 * Control plane page: makes the governance concept visible and measurable.
 *
 * Hybrid view -- the top is the always-visible architecture (the three planes
 * and the decision cycle Gateway -> Policy -> Risk -> Approval), the bottom is
 * the live proof: counts of verdicts (allow/deny/escalate), approval outcomes
 * (I6) and execution vs blocking, read from GET /control/summary. The summary
 * is a read-only, deterministic projection of the audit log (I1/I4); this page
 * never decides nor writes -- it shows what the Control plane decided.
 */

import { useEffect, useState } from "react";

import { getControlSummary } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import Mermaid from "../../components/help/Mermaid";
import type { ControlSummary } from "../../types/platform";
import "./control.css";

/** The three planes + the decision cycle (deny-by-default, I2 mediation, I6 block). */
const CONTROL_CHART = `flowchart LR
  AG["Agent"] -->|action| GW["Gateway<br/>normalise -> AgentActionEvent"]
  subgraph CONTROL["Control plane -- decide"]
    GW --> POL["Policy Engine<br/>deny-by-default"]
    POL --> RISK["Risk Engine<br/>sensibilite / blast radius"]
    RISK --> DEC{"verdict"}
    DEC -->|escalate| APP["Approval<br/>BLOQUE jusqu'a resolution (I6)"]
  end
  DEC -->|allow / approved| DATA["Data plane<br/>execute via proxy (I5)"]
  DEC -->|deny| BLOCK["bloque -- jamais execute"]
  APP -->|approved| DATA
  APP -->|denied / timeout| BLOCK
  DATA --> AUDIT["Audit plane<br/>event log append-only (I1)"]
  BLOCK --> AUDIT`;

interface StatProps {
  label: string;
  value: number;
  tone?: "ok" | "bad" | "warn" | "neutral";
}

function Stat({ label, value, tone = "neutral" }: StatProps): JSX.Element {
  return (
    <div className={`control-stat control-stat-${tone}`}>
      <span className="control-stat-value">{value}</span>
      <span className="control-stat-label">{label}</span>
    </div>
  );
}

export default function ControlPage(): JSX.Element {
  const [summary, setSummary] = useState<ControlSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getControlSummary()
      .then(setSummary)
      .catch((e: unknown) => setError(String(e)));
  }, []);

  return (
    <section className="page control-page">
      <div className="page-head">
        <h1>Control plane</h1>
        <PageHelp topic="control" />
        <AssistButton topic="control.status" label="Etat du plan de controle" />
      </div>
      <p className="control-note">
        Le coeur de la gouvernance : chaque action agent est mediee par le Control plane
        (deny-by-default, I2) qui decide <strong>allow / deny / escalate</strong> ; une action
        escaladee <strong>bloque</strong> jusqu&apos;a approbation (I6). Le resume ci-dessous est
        une projection <strong>lecture seule</strong> du log d&apos;audit (I1), deterministe (I4).
      </p>

      <Mermaid chart={CONTROL_CHART} title="Les trois plans + le cycle de decision" />

      {error !== null && <p className="control-error">{error}</p>}

      {summary !== null && (
        <div className="control-summary" data-testid="control-summary">
          <h2>Decisions (sur {summary.total} action(s) jugee(s))</h2>
          <div className="control-stats">
            <Stat label="allow" value={summary.verdicts.allow} tone="ok" />
            <Stat label="escalate" value={summary.verdicts.escalate} tone="warn" />
            <Stat label="deny" value={summary.verdicts.deny} tone="bad" />
          </div>
          <h2>Approbations (I6)</h2>
          <div className="control-stats">
            <Stat label="pending" value={summary.approvals.pending} tone="warn" />
            <Stat label="approved" value={summary.approvals.approved} tone="ok" />
            <Stat label="denied" value={summary.approvals.denied} tone="bad" />
            <Stat label="timeout" value={summary.approvals.timeout} tone="bad" />
          </div>
          <h2>Execution (I5)</h2>
          <div className="control-stats">
            <Stat label="executees" value={summary.executed} tone="ok" />
            <Stat label="bloquees" value={summary.denied_execution} tone="bad" />
          </div>
          {summary.deny_by_default && (
            <p className="control-posture" data-testid="control-deny-by-default">
              Posture : <strong>deny-by-default</strong> -- une action non couverte par une policy
              est refusee (fail-safe, jamais fail-open).
            </p>
          )}
        </div>
      )}
    </section>
  );
}
