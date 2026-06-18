/**
 * Metrics page: operational metrics over the captured LLM traces.
 *
 * Per-agent and per-tool call counts, error rate, latency percentiles
 * (p50/p95/p99), token totals and cost (USD when a pricing table is set), from
 * GET /metrics/summary. These are operational metrics ABOUT runs (derived from
 * captured latency/token values), not a decision/judge path -- read-only.
 */

import { useEffect, useState } from "react";

import { getMetricsSummary } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import type { MetricGroup, MetricsSummary } from "../../types/platform";
import "./metrics.css";

const COLS = ["calls", "err %", "p50 ms", "p95 ms", "p99 ms", "tokens", "cost $"] as const;

function cells(g: MetricGroup): Array<string | number> {
  return [
    g.calls,
    `${Math.round(g.error_rate * 100)}%`,
    g.latency_ms.p50,
    g.latency_ms.p95,
    g.latency_ms.p99,
    g.total_tokens,
    g.cost_usd === null ? "—" : g.cost_usd.toFixed(4),
  ];
}

function MetricsTable({
  title,
  testid,
  rows,
}: {
  title: string;
  testid: string;
  rows: Record<string, MetricGroup>;
}): JSX.Element {
  const keys = Object.keys(rows);
  return (
    <div className="metrics-block">
      <h2>{title}</h2>
      {keys.length === 0 ? (
        <p className="metrics-empty">Aucune donnee.</p>
      ) : (
        <table className="metrics-table" data-testid={testid}>
          <thead>
            <tr>
              <th>{title.split(" ")[1] ?? "id"}</th>
              {COLS.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k} className={rows[k].health === "degraded" ? "metrics-row-degraded" : ""}>
                <td className="metrics-id">
                  <span
                    className={`metrics-health metrics-health-${rows[k].health}`}
                    title={rows[k].health === "degraded" ? "taux d'erreur eleve" : "sain"}
                  />
                  {k}
                </td>
                {cells(rows[k]).map((v, i) => (
                  <td key={i} className={i === 1 && rows[k].error_rate > 0 ? "metrics-err" : ""}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function MetricsPage(): JSX.Element {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMetricsSummary()
      .then(setSummary)
      .catch((e: unknown) => setError(String(e)));
  }, []);

  return (
    <section className="page metrics-page">
      <div className="page-head">
        <h1>Metriques</h1>
        <PageHelp topic="metrics" />
      </div>
      <p className="metrics-note">
        Metriques operationnelles sur les traces LLM <strong>capturees</strong> (surface hook,
        in-process) : volume, taux d&apos;erreur, latence (p50/p95/p99), tokens et cout. Vue
        lecture seule, par agent et par outil -- pas un chemin de decision.
      </p>
      {error && <p className="metrics-error">{error}</p>}
      {summary !== null && (
        <>
          <div className="metrics-totals" data-testid="metrics-totals">
            <span className="metrics-total-item">{summary.totals.calls} appel(s)</span>
            <span className="metrics-total-item">
              {Math.round(summary.totals.error_rate * 100)}% erreur
            </span>
            <span className="metrics-total-item">{summary.totals.total_tokens} tokens</span>
            <span className="metrics-total-item">
              cout {summary.totals.cost_usd === null ? "—" : `$${summary.totals.cost_usd.toFixed(4)}`}
            </span>
          </div>
          <MetricsTable title="Par agent" testid="metrics-agents" rows={summary.agents} />
          <MetricsTable title="Par outil" testid="metrics-tools" rows={summary.tools} />
        </>
      )}
    </section>
  );
}
