/**
 * Proxy page -- debug console over the side-effect proxy traces (I5).
 *
 * Left: the list of recorded executions (one line per side effect, seq order).
 * Right: a Monaco read-only viewer showing either the selected trace (pretty
 * JSON) or the whole buffer as JSONL ("stream" mode). Read-only end to end: a
 * trace is a view over an effect that already happened (I1); this page never
 * mutates one. The buffer can be cleared (it is jettable; the audit log is not).
 *
 * Debug tracing is parametrable (R5): when INSPECT_IA_AGENTS_PROXY_DEBUG is off the
 * backend records nothing and the page says so instead of showing an empty list
 * as if it were a steady state.
 */

import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";

import { clearProxyTraces, getProxyTraces } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import type { ProxyTrace } from "../../types/platform";
import {
  distinctValues,
  failureCount,
  filterTraces,
  type ProxyTraceFilter,
  traceJson,
  tracesToJsonl,
  traceToLine,
} from "./proxyTraceModel";
import "./proxy.css";

const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));
const WirePanel = lazy(() => import("./WirePanel"));
const ReconcilePanel = lazy(() => import("./ReconcilePanel"));

const POLL_INTERVAL_MS = 2000;

type ViewerMode = "trace" | "stream";
/** Which side-effect altitude the page shows: the application-level ProxyTrace
 *  list ("app"), the network-level mitmproxy flows ("wire"), or the
 *  wire<->audit reconciliation that flags unmediated paths ("reconcile"). */
type Source = "app" | "wire" | "reconcile";

interface BoundaryState {
  error: Error | null;
}

/** Local boundary: a Monaco load failure degrades to a message, not a crash. */
class ViewerBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Render-path failure already captured in state; nothing else to do.
  }

  render(): ReactNode {
    if (this.state.error !== null) {
      return (
        <div className="proxy-viewer-msg" data-testid="proxy-viewer-error">
          editor failed to load: {this.state.error.message}
        </div>
      );
    }
    return this.props.children;
  }
}

export default function ProxyPage(): JSX.Element {
  const [source, setSource] = useState<Source>("app");
  const [traces, setTraces] = useState<ProxyTrace[]>([]);
  const [debugEnabled, setDebugEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [mode, setMode] = useState<ViewerMode>("trace");
  // Filter clauses (ephemeral UI state): narrow the list/stream by agent,
  // target or originating run (F3).
  const [agentId, setAgentId] = useState("");
  const [targetSystem, setTargetSystem] = useState("");
  const [runId, setRunId] = useState("");

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const res = await getProxyTraces();
      setTraces(res.traces);
      setDebugEnabled(res.debug_enabled);
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

  const onClear = useCallback(async (): Promise<void> => {
    try {
      await clearProxyTraces();
      setSelectedSeq(null);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [refresh]);

  const filter: ProxyTraceFilter = useMemo(
    () => ({
      agentId: agentId || undefined,
      targetSystem: targetSystem || undefined,
      runId: runId || undefined,
    }),
    [agentId, targetSystem, runId],
  );
  const shown = useMemo(() => filterTraces(traces, filter), [traces, filter]);
  const agentIds = useMemo(() => distinctValues(traces, "agent_id"), [traces]);
  const targetSystems = useMemo(() => distinctValues(traces, "target_system"), [traces]);
  const runIds = useMemo(() => distinctValues(traces, "run_id"), [traces]);
  const lines = useMemo(() => shown.map(traceToLine), [shown]);
  const fails = useMemo(() => failureCount(shown), [shown]);
  const viewerValue = useMemo(
    () => (mode === "stream" ? tracesToJsonl(shown) : traceJson(shown, selectedSeq)),
    [mode, shown, selectedSeq],
  );

  const onExport = useCallback((): void => {
    // Forensic snapshot of the CURRENTLY shown traces (bounded by the ring).
    const blob = new Blob([`${tracesToJsonl(shown)}\n`], { type: "application/x-ndjson" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "proxy-traces.jsonl";
    anchor.click();
    URL.revokeObjectURL(url);
  }, [shown]);

  return (
    <section className="proxy-page">
      <header className="proxy-header">
        <h1>Proxy</h1>
        <PageHelp topic="proxy" />
        <span className="proxy-source" role="group" aria-label="source">
          <button
            type="button"
            className="proxy-mode-btn"
            data-active={source === "app"}
            onClick={() => setSource("app")}
          >
            traces app
          </button>
          <button
            type="button"
            className="proxy-mode-btn"
            data-active={source === "wire"}
            onClick={() => setSource("wire")}
          >
            wire (mitmproxy)
          </button>
          <button
            type="button"
            className="proxy-mode-btn"
            data-active={source === "reconcile"}
            onClick={() => setSource("reconcile")}
          >
            reconciliation
          </button>
        </span>
        {source === "app" && (
          <>
            <span className="proxy-summary">
              {traces.length} trace(s), {fails} echec(s)
            </span>
            <span className="proxy-mode" role="group" aria-label="viewer mode">
              <button
                type="button"
                className="proxy-mode-btn"
                data-active={mode === "trace"}
                onClick={() => setMode("trace")}
              >
                trace
              </button>
              <button
                type="button"
                className="proxy-mode-btn"
                data-active={mode === "stream"}
                onClick={() => setMode("stream")}
              >
                stream
              </button>
            </span>
            <button type="button" className="proxy-export" onClick={onExport}>
              Export JSONL
            </button>
            <button type="button" className="proxy-clear" onClick={() => void onClear()}>
              Vider le tampon
            </button>
          </>
        )}
      </header>

      {source === "wire" && (
        <Suspense fallback={<div className="proxy-viewer-msg">loading wire panel...</div>}>
          <WirePanel />
        </Suspense>
      )}

      {source === "reconcile" && (
        <Suspense fallback={<div className="proxy-viewer-msg">loading reconcile panel...</div>}>
          <ReconcilePanel />
        </Suspense>
      )}

      {source === "app" && (
        <>
          <div className="proxy-filter" role="group" aria-label="trace filter">
        <label className="proxy-filter-label">
          agent_id
          <select
            className="proxy-filter-input"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
          >
            <option value="">tous</option>
            {agentIds.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label className="proxy-filter-label">
          target_system
          <select
            className="proxy-filter-input"
            value={targetSystem}
            onChange={(e) => setTargetSystem(e.target.value)}
          >
            <option value="">tous</option>
            {targetSystems.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="proxy-filter-label">
          run_id
          <select
            className="proxy-filter-input"
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
          >
            <option value="">tous</option>
            {runIds.map((r) => (
              <option key={r} value={r}>
                {r.slice(0, 12)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {debugEnabled === false && (
        <p className="proxy-banner" role="status">
          Mode debug desactive. Definir <code>INSPECT_IA_AGENTS_PROXY_DEBUG=on</code> cote
          backend pour enregistrer les traces du proxy (I5).
        </p>
      )}
      {error !== null && <p className="proxy-error">{error}</p>}

      <div className="proxy-grid">
        <ul className="proxy-list" aria-label="proxy traces">
          {lines.length === 0 && <li className="proxy-empty">aucune trace</li>}
          {lines.map((l) => (
            <li key={l.seq}>
              <button
                type="button"
                className="proxy-list-item"
                data-active={l.seq === selectedSeq}
                data-outcome={l.outcome}
                onClick={() => {
                  setMode("trace");
                  setSelectedSeq(l.seq);
                }}
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
            <div className="proxy-viewer">
              <ViewerBoundary>
                <Suspense
                  fallback={<div className="proxy-viewer-msg">loading editor...</div>}
                >
                  <MonacoJsonViewer value={viewerValue} />
                </Suspense>
              </ViewerBoundary>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
