/**
 * AppTracesPanel -- the application-level view of the Proxy console.
 *
 * Lists the recorded side-effect proxy executions (one line per effect, seq
 * order) and shows either the selected trace (pretty JSON) or the whole buffer
 * as JSONL ("stream" mode) in a read-only Monaco viewer. Read-only end to end
 * (I1): a trace is a view over an effect that already happened; this panel never
 * mutates one. The buffer can be cleared (it is jettable; the audit log is not).
 *
 * Data path: a 1s DELTA poll (useDeltaFeed + getProxyTracesDelta) fetches only
 * the rows past the server cursor, and every filter clause (agent/target/run/
 * outcome/free text) is pushed SERVER-SIDE as query params -- a filter change
 * restarts the feed (resetFeed) so the buffered rows always match the current
 * selection. The list itself is windowed (VirtualList) so a full client buffer
 * stays cheap to render, with tail-following while the poll is live.
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
import { useSearchParams } from "react-router-dom";

import { clearProxyTraces, getProxyTracesDelta, setProxyDebug } from "../../api/client";
import { VirtualList } from "../../components/VirtualList";
import type { ProxyTrace } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";
import { downloadFile } from "./proxyExport";
import {
  distinctValues,
  failureCount,
  traceJson,
  tracesToJsonl,
  traceToLine,
  type TraceLine,
} from "./proxyTraceModel";
import { useDeltaFeed, type DeltaEnvelope } from "./useDeltaFeed";

const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));

const POLL_INTERVAL_MS = 1000;
/** Fixed row height of a virtualized trace line; MUST match the
 *  `.proxy-vlist .proxy-list-item` height in proxy.css (windowing math). */
const ROW_HEIGHT_PX = 28;
/** Height of the windowed list viewport (replaces the old 60vh max-height:
 *  VirtualList needs a fixed pixel height for its slice arithmetic). */
const LIST_HEIGHT_PX = 420;

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
  const [debugEnabled, setDebugEnabled] = useState<boolean | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [mode, setMode] = useState<ViewerMode>("trace");
  // Filter clauses: agent/target/run/outcome stay ephemeral local UI state;
  // only the free-text `q` lives in the URL query string so a search is
  // deep-linkable + shareable (/proxy?q=open_pr opens pre-filtered).
  const [agentId, setAgentId] = useState("");
  const [targetSystem, setTargetSystem] = useState("");
  const [runId, setRunId] = useState("");
  const [outcome, setOutcome] = useState<"" | "ok" | "fail">("");
  const [params, setParams] = useSearchParams();
  const text = params.get("q") ?? "";

  // Set/delete only the `q` key, never the page-owned `source`/`run`.
  const setText = useCallback(
    (value: string): void => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) {
            next.set("q", value);
          } else {
            next.delete("q");
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  // The delta fetcher is rebuilt whenever a filter changes so it always reads
  // the CURRENT clause values (no stale closure). useDeltaFeed consumes the
  // fetcher through a ref, so a new identity does NOT tear down the poll
  // interval; the filter-change effect below restarts the feed instead.
  const fetcher = useCallback(
    (sinceSeq: number | null): Promise<DeltaEnvelope<ProxyTrace>> =>
      getProxyTracesDelta({
        sinceSeq: sinceSeq ?? undefined,
        agentId: agentId || undefined,
        target: targetSystem || undefined,
        runId: runId || undefined,
        outcome: outcome || undefined,
        q: text || undefined,
      }).then((res) => {
        // Side channel: every delta envelope carries debug_enabled, so the
        // recording state stays fresh WITHOUT a second status poll. The state
        // update runs in a promise callback (after commit, never during
        // render), so it is a safe place for this side effect.
        setDebugEnabled(res.debug_enabled);
        return { items: res.traces, last_seq: res.last_seq, reset: res.reset };
      }),
    [agentId, targetSystem, runId, outcome, text],
  );

  const { items, error: feedError, refresh, resetFeed } = useDeltaFeed<ProxyTrace>(fetcher, {
    intervalMs: POLL_INTERVAL_MS,
    paused: paused ?? false,
  });

  // Server-side filters: any clause change invalidates the cursor AND the
  // buffered rows (they belong to the previous selection), so the feed is
  // restarted. Skipped on mount -- the hook already fetches full there.
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    resetFeed();
  }, [agentId, targetSystem, runId, outcome, text, resetFeed]);

  // Headline status for the source menu. Gated on the first envelope so the
  // badge never flashes "off" before the backend has answered once.
  useEffect(() => {
    if (debugEnabled === null) {
      return;
    }
    onStatus?.({
      count: items.length,
      failed: failureCount(items),
      disabled: !debugEnabled,
    });
  }, [items, debugEnabled, onStatus]);

  // Follow UX: while the user is scrolled away from the tail, count the rows
  // that landed since they left; a badge lets them jump back to live tailing
  // by bumping the VirtualList scroll-to-tail signal.
  const [awayFromTail, setAwayFromTail] = useState(false);
  const [tailSignal, setTailSignal] = useState(0);
  // Latest-value ref so the (stable) scroll callback reads the current count.
  const itemCountRef = useRef(0);
  itemCountRef.current = items.length;
  const awayBaselineRef = useRef(0);
  const onScrollAwayFromTail = useCallback((away: boolean): void => {
    if (away) {
      awayBaselineRef.current = itemCountRef.current;
    }
    setAwayFromTail(away);
  }, []);
  const newSinceAway = awayFromTail ? Math.max(0, items.length - awayBaselineRef.current) : 0;
  const onResumeFollow = useCallback((): void => {
    setTailSignal((s) => s + 1);
    setAwayFromTail(false);
  }, []);

  const onClear = useCallback(async (): Promise<void> => {
    try {
      await clearProxyTraces();
      setSelectedSeq(null);
      setActionError(null);
      resetFeed();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }, [resetFeed]);

  // Toggle side-effect trace recording at runtime (operator action): flip the
  // backend switch then re-poll so the panel reflects the new state.
  const onToggleDebug = useCallback(async (): Promise<void> => {
    try {
      await setProxyDebug(!debugEnabled);
      setActionError(null);
      await refresh();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }, [debugEnabled, refresh]);

  // The select options derive from the CURRENTLY buffered (already filtered)
  // rows: once a clause is set the other options narrow with it. Accepted
  // trade-off of server-side filtering -- clearing the clause widens again.
  const agentIds = useMemo(() => distinctValues(items, "agent_id"), [items]);
  const targetSystems = useMemo(() => distinctValues(items, "target_system"), [items]);
  const runIds = useMemo(() => distinctValues(items, "run_id"), [items]);
  const lines = useMemo(() => items.map(traceToLine), [items]);
  const fails = useMemo(() => failureCount(items), [items]);
  const viewerValue = useMemo(
    () => (mode === "stream" ? tracesToJsonl(items) : traceJson(items, selectedSeq)),
    [mode, items, selectedSeq],
  );

  const onExport = useCallback((): void => {
    // Forensic snapshot of the CURRENTLY shown traces (bounded by the ring).
    downloadFile(`${tracesToJsonl(items)}\n`, "proxy-traces.jsonl", "application/x-ndjson");
  }, [items]);

  const itemKey = useCallback((l: TraceLine): number => l.seq, []);
  const renderRow = useCallback(
    (l: TraceLine): ReactNode => (
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
    ),
    [selectedSeq],
  );

  const shownError = actionError ?? feedError;

  return (
    <section className="proxy-app" data-testid="app-traces-panel">
      <div className="proxy-subheader">
        <span className="proxy-summary">
          {items.length} trace(s), {fails} echec(s)
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
        <label className="proxy-filter-label">
          recherche
          <input
            className="proxy-filter-input"
            type="search"
            data-testid="app-filter-text"
            placeholder="action / resource / payload / reponse"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
      </div>

      {debugEnabled === false && (
        <p className="proxy-banner" role="status">
          Mode debug desactive. Definir <code>INSPECT_IA_AGENTS_PROXY_DEBUG=on</code> cote
          backend pour enregistrer les traces du proxy (I5).
        </p>
      )}
      {shownError !== null && <p className="proxy-error">{shownError}</p>}

      <div className="proxy-grid">
        {/* The wrapper keeps the list role/label the page contract asserts on;
            the rows themselves are windowed by VirtualList. */}
        <div className="proxy-list proxy-vlist" role="list" aria-label="proxy traces">
          {newSinceAway > 0 && (
            <button
              type="button"
              className="proxy-new-badge"
              data-testid="proxy-new-traces"
              onClick={onResumeFollow}
            >
              {newSinceAway} nouvelles traces -- reprendre le suivi
            </button>
          )}
          {lines.length === 0 ? (
            <div className="proxy-empty">aucune trace</div>
          ) : (
            <VirtualList<TraceLine>
              items={lines}
              rowHeight={ROW_HEIGHT_PX}
              height={LIST_HEIGHT_PX}
              renderRow={renderRow}
              itemKey={itemKey}
              followTail={!paused}
              onScrollAwayFromTail={onScrollAwayFromTail}
              scrollToTailSignal={tailSignal}
              testId="proxy-trace-vlist"
            />
          )}
        </div>
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
