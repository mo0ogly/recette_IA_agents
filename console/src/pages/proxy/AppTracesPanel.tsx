/**
 * AppTracesPanel -- the application-level view of the Proxy console.
 *
 * Lists the recorded side-effect proxy executions (one line per effect, seq
 * order) and shows either the selected trace (pretty JSON) or the whole buffer
 * as JSONL ("stream" mode) in a read-only Monaco viewer. Read-only end to end
 * (I1): a trace is a view over an effect that already happened; this panel never
 * mutates one. The buffer can be cleared (it is jettable; the audit log is not).
 *
 * Debug tracing is parametrable (R5): when INSPECT_IA_AGENTS_PROXY_DEBUG is off the
 * backend records nothing and the panel says so instead of showing an empty list
 * as if it were a steady state.
 *
 * Self-contained source panel: it owns its own header actions (viewer mode,
 * export, clear) and reports its headline status up to the menu via `onStatus`
 * so the source registry stays evolutive (the orchestrator adds no per-source
 * branch).
 */

import {
  Component,
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ErrorInfo, ReactNode } from "react";

import { clearProxyTraces, getProxyTraces, setProxyDebug } from "../../api/client";
import type { ProxyTrace } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";
import { downloadFile } from "./proxyExport";
import {
  distinctValues,
  failureCount,
  filterTraces,
  type ProxyTraceFilter,
  traceJson,
  tracesToJsonl,
  traceToLine,
} from "./proxyTraceModel";

const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));

const POLL_INTERVAL_MS = 2000;

type ViewerMode = "trace" | "stream";

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

export default function AppTracesPanel({ onStatus, paused }: SourcePanelProps): JSX.Element {
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
  const [outcome, setOutcome] = useState<"" | "ok" | "fail">("");

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const res = await getProxyTraces();
      setTraces(res.traces);
      setDebugEnabled(res.debug_enabled);
      setError(null);
      onStatus?.({
        count: res.traces.length,
        failed: failureCount(res.traces),
        disabled: !res.debug_enabled,
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
      await clearProxyTraces();
      setSelectedSeq(null);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [refresh]);

  // Toggle side-effect trace recording at runtime (operator action): flip the
  // backend switch then re-poll so the panel reflects the new state.
  const onToggleDebug = useCallback(async (): Promise<void> => {
    try {
      await setProxyDebug(!debugEnabled);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [debugEnabled, refresh]);

  const filter: ProxyTraceFilter = useMemo(
    () => ({
      agentId: agentId || undefined,
      targetSystem: targetSystem || undefined,
      runId: runId || undefined,
      outcome: outcome || undefined,
    }),
    [agentId, targetSystem, runId, outcome],
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
    downloadFile(`${tracesToJsonl(shown)}\n`, "proxy-traces.jsonl", "application/x-ndjson");
  }, [shown]);

  return (
    <section className="proxy-app" data-testid="app-traces-panel">
      <div className="proxy-subheader">
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
        <button
          type="button"
          className="proxy-mode-btn"
          data-testid="proxy-debug-toggle"
          data-active={debugEnabled === true}
          onClick={() => void onToggleDebug()}
        >
          {debugEnabled
            ? "Enregistrement actif - desactiver"
            : "Activer l'enregistrement"}
        </button>
      </div>

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
        <label className="proxy-filter-label">
          issue
          <select
            className="proxy-filter-input"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as "" | "ok" | "fail")}
          >
            <option value="">toutes</option>
            <option value="ok">ok</option>
            <option value="fail">echec</option>
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
                <span className="proxy-action">{l.actionType}</span>
                <span className="proxy-label" title={`${l.target}/${l.resource}`}>
                  {l.target}/{l.resource}
                </span>
                <span className="proxy-status" data-outcome={l.outcome}>
                  {l.statusCode}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="proxy-viewer">
          <ViewerBoundary>
            <Suspense fallback={<div className="proxy-viewer-msg">loading editor...</div>}>
              <MonacoJsonViewer value={viewerValue} />
            </Suspense>
          </ViewerBoundary>
        </div>
      </div>
    </section>
  );
}
