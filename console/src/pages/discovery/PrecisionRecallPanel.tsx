/**
 * PrecisionRecallPanel — scores the eBPF discovery probe against the wire truth.
 *
 * Runs POST /probe/bench (a bounded probe capture joined to the buffered wire
 * flows by real IP:port) and shows the detector scorecard: recall (did the
 * scanner miss a real egress?), precision, F1, the TP/FN/FP counts, and a
 * per-endpoint table. FN rows are the load-bearing result — a real egress the
 * wire saw but the probe missed. Nothing is faked: undefined rates render "n/a"
 * and partial wire coverage (flows without an L3/L4 IP) is surfaced explicitly.
 */

import { useState } from "react";

import { runProbeBench, pct, verdictLabel } from "./benchModel";
import type { ProbeBenchResult } from "./benchModel";

export default function PrecisionRecallPanel(): JSX.Element {
  const [agents, setAgents] = useState("");
  const [durationMs, setDurationMs] = useState(3000);
  const [result, setResult] = useState<ProbeBenchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const run = (): void => {
    const ids = agents.split(",").map((a) => a.trim()).filter(Boolean);
    if (ids.length === 0) {
      setError("Renseigne au moins un agent (séparés par des virgules).");
      return;
    }
    setRunning(true);
    setError(null);
    runProbeBench(ids, durationMs)
      .then((r) => {
        setResult(r);
        setRunning(false);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
        setRunning(false);
      });
  };

  const report = result?.report ?? null;

  return (
    <section className="bench-panel" data-testid="bench-panel">
      <h2 className="bench-title">Banc d'essai — scanner eBPF vs vérité wire</h2>
      <p className="bench-note">
        Compare les connexions réelles détectées par la sonde (tokens
        <code> connect:ip:port</code>) à la vérité terrain du wire (IP:port réelle
        de chaque flux mitmproxy). Le <strong>rappel</strong> est la métrique clé :
        un flux wire non vu par la sonde (FN) est un egress fantôme manqué. La
        précision est plus indicative — le wire ne voit que le HTTP(S) proxifié.
      </p>

      <div className="bench-controls">
        <input
          type="text"
          className="bench-agents"
          placeholder="agents (ex. pr-bot, triage-agent)"
          value={agents}
          onChange={(e) => setAgents(e.target.value)}
          data-testid="bench-agents"
        />
        <label className="bench-duration">
          durée (ms)
          <input
            type="number"
            min={100}
            step={500}
            value={durationMs}
            onChange={(e) => setDurationMs(Number(e.target.value) || 3000)}
            data-testid="bench-duration"
          />
        </label>
        <button
          type="button"
          className="bench-run"
          onClick={run}
          disabled={running}
          data-testid="bench-run"
        >
          {running ? "Capture..." : "Lancer le bench"}
        </button>
      </div>

      {error && (
        <div className="bench-error" role="alert" data-testid="bench-error">
          {error}
        </div>
      )}

      {report && (
        <>
          <div className="bench-metrics" data-testid="bench-metrics">
            <div className="bench-metric bench-metric-recall">
              <span className="bench-metric-k">rappel</span>
              <span className="bench-metric-v">{pct(report.recall)}</span>
            </div>
            <div className="bench-metric">
              <span className="bench-metric-k">précision</span>
              <span className="bench-metric-v">{pct(report.precision)}</span>
            </div>
            <div className="bench-metric">
              <span className="bench-metric-k">F1</span>
              <span className="bench-metric-v">{pct(report.f1)}</span>
            </div>
            <div className="bench-metric bench-verdict-tp">
              <span className="bench-metric-k">TP</span>
              <span className="bench-metric-v">{report.tp}</span>
            </div>
            <div className="bench-metric bench-verdict-fn">
              <span className="bench-metric-k">FN (ghost)</span>
              <span className="bench-metric-v">{report.fn}</span>
            </div>
            <div className="bench-metric bench-verdict-fp">
              <span className="bench-metric-k">FP</span>
              <span className="bench-metric-v">{report.fp}</span>
            </div>
          </div>

          <p className="bench-coverage" data-testid="bench-coverage">
            {report.wire_endpoints} endpoint(s) wire · {report.probe_endpoints} endpoint(s) sonde ·{" "}
            {result?.wire_flows_total ?? 0} flux wire
            {report.wire_flows_without_ip > 0 && (
              <span className="bench-coverage-warn">
                {" "}
                — {report.wire_flows_without_ip} flux sans IP L3/L4 (overlay hérité, non joignables)
              </span>
            )}
          </p>

          <table className="bench-table" data-testid="bench-table">
            <thead>
              <tr>
                <th>Endpoint (IP:port)</th>
                <th>Verdict</th>
                <th>Hôte</th>
                <th>JA3</th>
              </tr>
            </thead>
            <tbody>
              {report.endpoints.map((e) => {
                const v = verdictLabel(e.verdict);
                return (
                  <tr key={e.endpoint} data-testid={`bench-row-${e.endpoint}`}>
                    <td className="bench-endpoint">{e.endpoint}</td>
                    <td>
                      <span className={`bench-badge bench-badge-${v.cls}`}>{v.text}</span>
                    </td>
                    <td>{e.host ?? "-"}</td>
                    <td className="bench-ja3">{e.ja3 ?? "-"}</td>
                  </tr>
                );
              })}
              {report.endpoints.length === 0 && (
                <tr>
                  <td colSpan={4} className="bench-empty">
                    Aucun endpoint observé (ni wire ni sonde) sur cette fenêtre.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
