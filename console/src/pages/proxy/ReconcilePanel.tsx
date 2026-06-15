/**
 * ReconcilePanel -- the wire<->audit reconciliation view of the Proxy page.
 *
 * Joins the network view (mitmproxy WireFlow) with the audit view (ProxyTrace)
 * by run: a wire flow that reached a NON-mediated target has no matching audit
 * event -- the ghost-agent / shadow-AI signal. The panel renders the verdict
 * (ok / bypass detected) and the offending flows (target host:port + path), so
 * an operator sees an unmediated egress without reading raw buffers.
 *
 * Read-only (I1): a reconciliation is a computed view over effects that already
 * happened; the lab OBSERVES the unmediated path, it never blocks it.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { getReconcile } from "../../api/client";
import type { ReconcileReport } from "../../types/platform";

const POLL_INTERVAL_MS = 2000;

export default function ReconcilePanel(): JSX.Element {
  const [report, setReport] = useState<ReconcileReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setReport(await getReconcile());
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

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
      </header>

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
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
