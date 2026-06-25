/**
 * BehaviorWavePanel -- the analyst's cockpit for the behavioral-analysis engine.
 *
 * The analyst tunes a profile (the four knobs: lenses, threat, thresholds) and runs
 * a *wave* over the current capture's recording via POST /behavior/wave. The result
 * is deterministic and replayable (the experiment_id pins evidence+profile+version),
 * so what the console shows is exactly what `recette analyze replay` reproduces.
 *
 * BehaviorReportView is presentational (pure props) so it renders against a real
 * captured payload in the R16 contract test; BehaviorWavePanel adds the editor +
 * the API call.
 */

import { useState } from "react";
import {
  runBehaviorWave,
  type BehaviorProfile,
  type BehaviorWaveResult,
  type BehaviorAgentReport,
  type BehaviorMetrics,
} from "../../api/client";

const ALL_LENSES = [
  "egress",
  "dns",
  "credential",
  "doh",
  "process",
  "said_scope",
  "sequence",
  "baseline",
];
const THREATS = ["neutral", "exfil", "escalation", "tunneling", "supply_chain"];

function Cols({ a }: { a: BehaviorAgentReport }): JSX.Element {
  const done = [
    ...a.done.dialed_servers.map((s) => `dial ${s}`),
    ...(a.done.doh_egress ?? []).map((s) => `DoH ${s}:443`),
    ...(a.done.credential_opens ?? []).map((p) => `CREDENTIAL ${p}`),
    ...a.done.undeclared_egress.map((s) => `EGRESS ${s}`),
    ...a.done.undeclared_dns.map((s) => `DNS ${s}`),
    ...(a.done.process_spawned ? ["spawned a child process"] : []),
  ];
  const col = (title: string, items: string[]) => (
    <div className="bw-col">
      <h6>{title}</h6>
      {items.length === 0 ? <span className="bw-empty">none</span> : <ul>{items.map((i) => <li key={i}>{i}</li>)}</ul>}
    </div>
  );
  return (
    <div className="bw-cols">
      {col("PLANNED", [...a.planned.systems, ...a.planned.scope])}
      {col("SAID", a.said ? a.said.actions : ["(unlinked)"])}
      {col("DONE", done)}
    </div>
  );
}

function MetricsView({ m }: { m: BehaviorMetrics }): JSX.Element {
  const c = m.confusion;
  return (
    <div className="bw-metrics" data-testid="bw-metrics">
      <h5>Research metrics</h5>
      <p>
        TP={c.tp} FP={c.fp} FN={c.fn} TN={c.tn} &middot; precision={c.precision} recall={c.recall}{" "}
        F1={c.f1}
      </p>
      <p>
        separation AUC=<strong>{m.separation_auc}</strong> &middot; ROC AUC={m.roc.auc}
      </p>
      <p className="bw-standards">
        {Object.entries(m.standards_distribution.owasp_asi).map(([k, v]) => (
          <span key={k} className="bw-tag">
            {k}:{v}
          </span>
        ))}
      </p>
    </div>
  );
}

export function BehaviorReportView({ result }: { result: BehaviorWaveResult }): JSX.Element {
  const { report, metrics } = result;
  return (
    <section className="bw-result" data-testid="behavior-result">
      <header className="bw-head">
        <span>
          wave <strong>{report.profile_name}</strong> &middot; threat {report.threat}
        </span>
        <code className="bw-eid" title="evidence | profile | version">
          {report.experiment_id}
        </code>
      </header>
      {report.agents.map((a) => (
        <article key={a.agent_id} className="bw-agent" data-testid={`bw-agent-${a.agent_id}`}>
          <div className="bw-agent-head">
            <span className="bw-id">{a.agent_id}</span>
            <span className={`bw-score bw-score-${a.behavioral_score < 60 ? "bad" : "ok"}`}>
              score {a.behavioral_score}
            </span>
            <span
              className={a.coherent ? "bw-ok" : "bw-divergent"}
              data-testid={`bw-verdict-${a.agent_id}`}
            >
              {a.coherent ? "coherent" : "DIVERGENT"}
            </span>
          </div>
          <Cols a={a} />
          <ul className="bw-findings">
            {a.findings.map((f, i) => (
              <li key={`${f.lens}-${i}`} className={`bw-find bw-${f.severity}`}>
                <span className="bw-sev">{f.severity.toUpperCase()}</span>
                <span className="bw-flog">{f.log}</span>
                <span className="bw-tag">
                  {[f.owasp_asi, f.mitre_atlas].filter(Boolean).join(" / ")}
                </span>
              </li>
            ))}
          </ul>
        </article>
      ))}
      {metrics && <MetricsView m={metrics} />}
    </section>
  );
}

export default function BehaviorWavePanel({
  recording,
}: {
  recording: unknown;
}): JSX.Element | null {
  const [lenses, setLenses] = useState<string[]>(ALL_LENSES);
  const [threat, setThreat] = useState("exfil");
  const [tolerance, setTolerance] = useState(0);
  const [scope, setScope] = useState("strict");
  const [cohort, setCohort] = useState<"all" | "detected" | "flagged">("all");
  const [result, setResult] = useState<BehaviorWaveResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!recording) return null;

  const toggle = (lens: string) =>
    setLenses((cur) => (cur.includes(lens) ? cur.filter((l) => l !== lens) : [...cur, lens]));

  const run = async () => {
    setBusy(true);
    setError(null);
    const profile: BehaviorProfile = {
      name: `console-${threat}`,
      lenses,
      threat,
      thresholds: { ghost_host_tolerance: tolerance, scope },
      cohort: cohort === "all" ? undefined : { discovery: cohort },
    };
    try {
      setResult(await runBehaviorWave(recording, profile));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="bw-panel" data-testid="behavior-wave-panel">
      <h4>Behavioral analysis -- run a tunable wave on this capture</h4>
      <div className="bw-editor">
        <fieldset className="bw-lenses">
          <legend>lenses</legend>
          {ALL_LENSES.map((lens) => (
            <label key={lens}>
              <input type="checkbox" checked={lenses.includes(lens)} onChange={() => toggle(lens)} />
              {lens}
            </label>
          ))}
        </fieldset>
        <label className="bw-knob">
          threat
          <select value={threat} onChange={(e) => setThreat(e.target.value)}>
            {THREATS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="bw-knob">
          ghost-host tolerance
          <input
            type="number"
            min={0}
            value={tolerance}
            onChange={(e) => setTolerance(Number(e.target.value))}
          />
        </label>
        <label className="bw-knob">
          scope
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="strict">strict</option>
            <option value="lax">lax</option>
          </select>
        </label>
        <label className="bw-knob">
          cohort
          <select
            value={cohort}
            onChange={(e) => setCohort(e.target.value as "all" | "detected" | "flagged")}
            data-testid="bw-cohort-select"
          >
            <option value="all">All</option>
            <option value="detected">Discovered</option>
            <option value="flagged">Flagged</option>
          </select>
        </label>
        <button type="button" onClick={run} disabled={busy}>
          {busy ? "running..." : "Run wave"}
        </button>
      </div>
      {error && <p className="bw-error">{error}</p>}
      {result?.cohort?.mode && (
        <p className="bw-cohort-line" data-testid="bw-cohort-line">
          cohort: {result.cohort.mode} &rarr; {result.cohort.agents.length} agent(s)
          {result.cohort.agents.length > 0 && (
            <span className="bw-cohort-agents"> ({result.cohort.agents.join(", ")})</span>
          )}
        </p>
      )}
      {result && <BehaviorReportView result={result} />}
    </section>
  );
}
