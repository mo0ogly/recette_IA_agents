/**
 * ReconcilePanel -- the wire<->audit reconciliation view of the Proxy page.
 *
 * Joins the network view (mitmproxy WireFlow) with the audit view (ProxyTrace)
 * by run: a wire flow that reached a NON-mediated target has no matching audit
 * event -- the ghost-agent / shadow-AI signal. The panel renders the verdict
 * (ok / bypass detected) and the offending flows (target host:port + path), so
 * an operator sees an unmediated egress without reading raw buffers.
 *
 * Polling the verdict is read-only. The ONE mutating action is "raise": it
 * records each detected bypass as a compensatory event in the append-only audit
 * log (I1, never a mutation) -- the Control Plane alert. The lab OBSERVES the
 * unmediated path and now JOURNALS it; it still never blocks it.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { getReconcile, raiseReconcile } from "../../api/client";
import type { ReconcileReport } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";

const POLL_INTERVAL_MS = 2000;

export default function ReconcilePanel({ onStatus }: SourcePanelProps): JSX.Element {
  const [report, setReport] = useState<ReconcileReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [raising, setRaising] = useState(false);
  const [raiseMsg, setRaiseMsg] = useState<string | null>(null);
  // Phase-3 toggle: per-flow side_effect_hash join (catches a ghost via an
  // allowlisted target). Off = phase-2 target/run join.
  const [strict, setStrict] = useState(false);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const res = await getReconcile(undefined, strict);
      setReport(res);
      setError(null);
      onStatus?.({ count: res.bypass_flows.length, failed: res.bypass_flows.length });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [strict, onStatus]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const onRaise = useCallback(async (): Promise<void> => {
    setRaising(true);
    try {
      const res = await raiseReconcile(undefined, strict);
      setRaiseMsg(
        res.raised > 0
          ? `${res.raised} evenement(s) consigne(s) au journal d'audit`
          : "deja consigne (aucun nouvel evenement)",
      );
      setError(null);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRaising(false);
    }
  }, [refresh, strict]);

  const bypass = useMemo(() => report?.bypass_flows ?? [], [report]);
  const audited = useMemo(() => report?.audited_run_ids ?? [], [report]);

  return (
    <section className="proxy-reconcile" data-testid="reconcile-panel">
      <header className="proxy-header">
        {report === null ? (
          <span className="proxy-summary">reconciliation en cours...</span>
        ) : report.ok ? (
          <span
            className="proxy-badge"
            data-outcome="ok"
            role="status"
            data-testid="reconcile-ok"
          >
            aucun chemin non-medie
          </span>
        ) : (
          <span
            className="proxy-badge"
            data-outcome="fail"
            role="status"
            data-testid="reconcile-bypass"
          >
            bypass detecte : {bypass.length} flux non-medie(s)
          </span>
        )}
        {audited.length > 0 && (
          <span className="proxy-summary" data-testid="reconcile-audited">
            runs audites : {audited.join(", ")}
          </span>
        )}
        <label className="proxy-summary" data-testid="reconcile-strict-toggle">
          <input
            type="checkbox"
            checked={strict}
            onChange={(e) => setStrict(e.target.checked)}
          />{" "}
          strict (hash par flux)
        </label>
        {report !== null && !report.ok && (
          <button
            type="button"
            className="proxy-clear"
            data-testid="reconcile-raise"
            disabled={raising}
            onClick={() => void onRaise()}
          >
            {raising ? "consignation..." : "Consigner au journal d'audit"}
          </button>
        )}
      </header>

      {raiseMsg !== null && (
        <p className="proxy-banner" role="status" data-testid="reconcile-raise-msg">
          {raiseMsg}
        </p>
      )}
      {error !== null && <p className="proxy-error">{error}</p>}

      <p className="proxy-banner" role="note">
        Un flux reseau vers une cible non-mediee n&apos;a aucun evenement d&apos;audit
        correspondant : c&apos;est le signal d&apos;un agent fantome (ecriture directe,
        hors proxy gouverne). Le lab l&apos;OBSERVE, il ne le bloque pas.
      </p>

      {report !== null && report.ok && (
        <p className="proxy-empty" data-testid="reconcile-clean">
          tous les flux observes correspondent a une cible mediee.
        </p>
      )}

      {bypass.length > 0 && (
        <table className="proxy-reconcile-table" aria-label="bypass flows">
          <thead>
            <tr>
              <th>seq</th>
              <th>cible</th>
              <th>chemin</th>
              <th>run</th>
              <th>raison</th>
            </tr>
          </thead>
          <tbody>
            {bypass.map((f) => (
              <tr key={f.seq} data-testid="reconcile-row">
                <td>#{f.seq}</td>
                <td>
                  <code>
                    {f.host}:{f.port}
                  </code>
                </td>
                <td>{f.path}</td>
                <td>{f.run_id ?? "-"}</td>
                <td>{f.bypass_reason ?? "non_mediated_target"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
