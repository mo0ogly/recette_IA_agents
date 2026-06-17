/**
 * WirePanel -- the wire-overlay (mitmproxy) view of the Proxy page.
 *
 * Shows the NETWORK-level flows captured by the OPTIONAL mitmproxy Docker
 * overlay (the bytes on the wire of agent -> target traffic), as opposed to the
 * application-level ProxyTrace list on the main page. Read-only end to end (I1):
 * a flow describes an exchange that already happened; the panel only views and
 * clears the jettable buffer.
 *
 * When the overlay is not configured (INSPECT_IA_AGENTS_WIRE_PROXY unset) the panel
 * says so and how to enable it, instead of showing an empty list as a steady
 * state. The bodies are rendered in a plain read-only pane (no Monaco): the
 * request/response payloads are the point, and a plain pane renders under jsdom.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { clearWireFlows, getWireFlows } from "../../api/client";
import ProxySelector from "../../components/ProxySelector";
import type { WireFlow } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";
import { wireFailureCount, wireFlowToLine } from "./wireFlowModel";

const POLL_INTERVAL_MS = 2000;

export default function WirePanel({ onStatus }: SourcePanelProps): JSX.Element {
  const [flows, setFlows] = useState<WireFlow[]>([]);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [proxyUrl, setProxyUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const res = await getWireFlows();
      setFlows(res.flows);
      setEnabled(res.enabled);
      setProxyUrl(res.proxy_url);
      setError(null);
      onStatus?.({
        count: res.flows.length,
        failed: wireFailureCount(res.flows),
        disabled: !res.enabled,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [onStatus]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const onClear = useCallback(async (): Promise<void> => {
    try {
      await clearWireFlows();
      setSelectedSeq(null);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [refresh]);

  const lines = useMemo(() => flows.map(wireFlowToLine), [flows]);
  const fails = useMemo(() => wireFailureCount(flows), [flows]);
  const selected = useMemo(
    () => flows.find((f) => f.seq === selectedSeq) ?? null,
    [flows, selectedSeq],
  );

  return (
    <section className="proxy-wire" data-testid="wire-panel">
      <header className="proxy-header">
        <ProxySelector />
        <span className="proxy-summary">
          {flows.length} flux, {fails} echec(s)
        </span>
        {enabled === true && proxyUrl !== null && (
          <span className="proxy-wire-proxy" data-testid="wire-proxy-url">
            proxy: <code>{proxyUrl}</code>
          </span>
        )}
        <button type="button" className="proxy-clear" onClick={() => void onClear()}>
          Vider le tampon
        </button>
      </header>

      {enabled === false && (
        <p className="proxy-banner" role="status" data-testid="wire-disabled">
          Surcouche wire desactivee. Demarrer mitmproxy avec
          <code> ./recette.sh wire up</code>, puis exporter
          <code> INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:8083</code> et relancer
          l&apos;API (<code>./recette.sh api restart</code>) pour router les agents
          au travers.
        </p>
      )}
      {error !== null && <p className="proxy-error">{error}</p>}

      <div className="proxy-grid">
        <ul className="proxy-list" aria-label="wire flows">
          {lines.length === 0 && <li className="proxy-empty">aucun flux</li>}
          {lines.map((l) => (
            <li key={l.seq}>
              <button
                type="button"
                className="proxy-list-item"
                data-active={l.seq === selectedSeq}
                data-outcome={l.outcome}
                onClick={() => setSelectedSeq(l.seq)}
              >
                <span className="proxy-seq">#{l.seq}</span>
                <span className="proxy-badge" data-outcome={l.outcome}>
                  {l.outcome}
                </span>
                <span className="proxy-label">{l.label}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="proxy-viewer proxy-wire-detail">
          {selected === null ? (
            <p className="proxy-viewer-msg">selectionner un flux a gauche</p>
          ) : (
            <dl className="proxy-wire-kv" data-testid="wire-detail">
              <dt>requete</dt>
              <dd>
                {selected.method} {selected.scheme}://{selected.host}:{selected.port}
                {selected.path}
              </dd>
              <dt>statut</dt>
              <dd>{selected.status_code}</dd>
              <dt>content-type</dt>
              <dd>{selected.content_type || "-"}</dd>
              <dt>corps requete</dt>
              <dd>
                <pre className="proxy-wire-body">{selected.request_body || "(vide)"}</pre>
              </dd>
              <dt>corps reponse</dt>
              <dd>
                <pre className="proxy-wire-body">{selected.response_body || "(vide)"}</pre>
              </dd>
            </dl>
          )}
        </div>
      </div>
    </section>
  );
}
