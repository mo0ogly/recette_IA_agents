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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { clearWireFlows, controlWireOverlay, getWireFlows } from "../../api/client";
import ProxySelector from "../../components/ProxySelector";
import type { WireFlow } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";
import { wireFlowToCurl } from "./curl";
import { downloadFile, flowsToHar, toJsonl } from "./proxyExport";
import {
  distinctWireValues,
  filterWireFlows,
  type WireFlowFilter,
  wireFailureCount,
  wireFlowToLine,
} from "./wireFlowModel";

const POLL_INTERVAL_MS = 2000;

export default function WirePanel({ onStatus, paused }: SourcePanelProps): JSX.Element {
  const [flows, setFlows] = useState<WireFlow[]>([]);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [proxyUrl, setProxyUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [nextStep, setNextStep] = useState<string | null>(null);
  const [busy, setBusy] = useState<boolean>(false);

  // Filter clauses live in the URL query string (deep-linkable + shareable):
  // host/method/status/q (free text) own their own keys, plus a read of the
  // page-owned `run`. The derived filter is the single source of truth -- there
  // is no duplicate local state for these keys. The status reported up via
  // onStatus stays on the FULL buffer, not the filtered view.
  const [params, setParams] = useSearchParams();
  const filter: WireFlowFilter = useMemo(
    () => ({
      host: params.get("host") ?? undefined,
      method: params.get("method") ?? undefined,
      status: params.get("status") ?? undefined,
      runId: params.get("run") ?? undefined,
      text: params.get("q") ?? undefined,
    }),
    [params],
  );

  // Set/delete ONE query key without clobbering the others (notably the
  // page-owned `source` and `run`): WirePanel only ever writes host/method/
  // status/q. `replace` keeps filtering out of the back/forward history.
  const setParam = useCallback(
    (key: string, value: string): void => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) {
            next.set(key, value);
          } else {
            next.delete(key);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

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

  // Read `paused` from a ref inside the tick so toggling pause does NOT tear
  // down and re-run the effect (which would re-fire the initial fetch). The
  // initial fetch runs once on mount; only the recurring tick is gated.
  const pausedRef = useRef(paused);
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      if (!pausedRef.current) {
        void refresh();
      }
    }, POLL_INTERVAL_MS);
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

  const onToggleOverlay = useCallback(async (): Promise<void> => {
    setBusy(true);
    try {
      const res = await controlWireOverlay(enabled === true ? "down" : "up");
      setNextStep(res.next_step);
      setError(null);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [enabled, refresh]);

  // Filtered view drives the list, the detail selection and the exports; the
  // full `flows` set still feeds the select options and the header counts.
  const shown = useMemo(() => filterWireFlows(flows, filter), [flows, filter]);
  const hosts = useMemo(() => distinctWireValues(flows, "host"), [flows]);
  const methods = useMemo(() => distinctWireValues(flows, "method"), [flows]);
  const runIds = useMemo(() => distinctWireValues(flows, "run_id"), [flows]);
  const lines = useMemo(() => shown.map(wireFlowToLine), [shown]);
  const fails = useMemo(() => wireFailureCount(flows), [flows]);
  const selected = useMemo(
    () => shown.find((f) => f.seq === selectedSeq) ?? null,
    [shown, selectedSeq],
  );

  const onExportJsonl = useCallback((): void => {
    // Forensic snapshot of the CURRENTLY shown flows (bounded by the ring).
    downloadFile(`${toJsonl(shown)}\n`, "wire-flows.jsonl", "application/x-ndjson");
  }, [shown]);

  const onExportHar = useCallback((): void => {
    downloadFile(flowsToHar(shown), "wire-flows.har", "application/json");
  }, [shown]);

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
        <button
          type="button"
          className="proxy-clear"
          data-testid="wire-overlay-toggle"
          disabled={busy}
          onClick={() => void onToggleOverlay()}
        >
          {enabled === true ? "Arreter le reseau (wire)" : "Demarrer le reseau (wire)"}
        </button>
        <button type="button" className="proxy-export" onClick={onExportJsonl}>
          Export JSONL
        </button>
        <button
          type="button"
          className="proxy-export"
          data-testid="wire-export-har"
          onClick={onExportHar}
        >
          Export HAR
        </button>
        <button type="button" className="proxy-clear" onClick={() => void onClear()}>
          Vider le tampon
        </button>
      </header>

      <div className="proxy-filter" role="group" aria-label="wire filter">
        <label className="proxy-filter-label">
          host
          <select
            className="proxy-filter-input"
            value={filter.host ?? ""}
            onChange={(e) => setParam("host", e.target.value)}
          >
            <option value="">tous</option>
            {hosts.map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </select>
        </label>
        <label className="proxy-filter-label">
          method
          <select
            className="proxy-filter-input"
            value={filter.method ?? ""}
            onChange={(e) => setParam("method", e.target.value)}
          >
            <option value="">toutes</option>
            {methods.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="proxy-filter-label">
          status
          <input
            className="proxy-filter-input"
            type="text"
            data-testid="wire-filter-status"
            value={filter.status ?? ""}
            onChange={(e) => setParam("status", e.target.value)}
          />
        </label>
        <label className="proxy-filter-label">
          run_id
          {/* `run` is page-owned (set by the cockpit "Voir dans le proxy"
              deep-link). This panel READS it to narrow the flows; it only ever
              SETS run (selecting a run), it never deletes it -- so an empty
              selection is a no-op rather than clobbering the page's run. */}
          <select
            className="proxy-filter-input"
            value={filter.runId ?? ""}
            onChange={(e) => {
              if (e.target.value) {
                setParam("run", e.target.value);
              }
            }}
          >
            <option value="">tous</option>
            {runIds.map((r) => (
              <option key={r} value={r}>
                {r.slice(0, 12)}
              </option>
            ))}
          </select>
        </label>
        <label className="proxy-filter-label">
          texte
          <input
            className="proxy-filter-input"
            type="text"
            data-testid="wire-filter-text"
            value={filter.text ?? ""}
            onChange={(e) => setParam("q", e.target.value)}
          />
        </label>
      </div>

      {nextStep !== null && (
        <p className="proxy-banner" role="status" data-testid="wire-next-step">
          {nextStep}
        </p>
      )}

      {/* Flows can arrive via the transport-route registry even when
          INSPECT_IA_AGENTS_WIRE_PROXY is unset (enabled=false); yield the
          how-to-enable banner to actual data. */}
      {enabled === false && flows.length === 0 && (
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
              <dt>replay</dt>
              <dd>
                <button
                  type="button"
                  className="proxy-export"
                  data-testid="wire-copy-curl"
                  onClick={() => void navigator.clipboard?.writeText(wireFlowToCurl(selected))}
                >
                  Copy curl
                </button>
              </dd>
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
