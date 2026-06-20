/**
 * SessionsPanel -- the "sessions" source of the Proxy console.
 *
 * Groups the recorded side-effect traces into agent<->server SESSIONS (by run,
 * agent, or agent+target) and shows them with progressive disclosure: a session
 * list (left) -> the selected session's exchange timeline (right) -> per
 * exchange a compact summary that expands to the req<->resp pair -> the full raw
 * trace in a read-only Monaco viewer on demand. Read-only end to end (I1/I5):
 * every view is over an effect that already happened; this panel never mutates
 * one. Concurrency-safe: selection is held by session KEY (not index), so a new
 * concurrent run arriving on the next poll never steals the current selection,
 * and an aged-out selection degrades to a hint, not a crash.
 *
 * Live: V1 reuses the lightweight poll (2s). The SSE mode is opt-in and wired in
 * phase 2; the selector renders it disabled until then.
 */

import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { getProxyTraces, getWireFlows } from "../../api/client";
import type { ProxyTrace, WireFlow } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";
import {
  type Exchange,
  type GroupKey,
  groupSessions,
  type Session,
  sessionsFailed,
} from "./sessionModel";

const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));

const POLL_INTERVAL_MS = 2000;
type LiveMode = "poll" | "sse";

interface BoundaryState {
  error: Error | null;
}

/** Local boundary: a Monaco load failure degrades to a message, not a crash. */
class ViewerBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };
  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }
  componentDidCatch(_e: Error, _i: ErrorInfo): void {}
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

export default function SessionsPanel({ onStatus }: SourcePanelProps): JSX.Element {
  const [traces, setTraces] = useState<ProxyTrace[]>([]);
  const [debugEnabled, setDebugEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [groupKey, setGroupKey] = useState<GroupKey>("run");
  const [liveMode, setLiveMode] = useState<LiveMode>("poll");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [expandedSeq, setExpandedSeq] = useState<number | null>(null);
  const [detailSeq, setDetailSeq] = useState<number | null>(null);
  const [wireFlows, setWireFlows] = useState<WireFlow[]>([]);
  const [wireSeq, setWireSeq] = useState<number | null>(null);

  // Deep-link: ?run=<run_id> auto-selects that run's session without a click,
  // so a "Voir dans le proxy" button from the cockpit lands on its exchanges.
  // Selection holds by key, so if the session is not in the ring yet it still
  // selects when it arrives on a later poll; aged-out degrades to the hint.
  const [searchParams] = useSearchParams();
  const runParam = searchParams.get("run");
  useEffect(() => {
    if (runParam) {
      setGroupKey("run");
      setSelectedKey(runParam);
    }
  }, [runParam]);

  // Keep the latest onStatus without making it an effect dependency: a parent
  // passing an inline callback must not retrigger the status effect (loop guard).
  const onStatusRef = useRef(onStatus);
  useEffect(() => {
    onStatusRef.current = onStatus;
  }, [onStatus]);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const res = await getProxyTraces();
      setTraces(res.traces);
      setDebugEnabled(res.debug_enabled);
      setError(null);
      // Wire overlay is optional: when the overlay is off (or the fetch fails)
      // the traces must still render, so this never propagates to the panel.
      try {
        const w = await getWireFlows();
        setWireFlows(w.flows);
      } catch {
        setWireFlows([]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
    if (liveMode !== "poll") {
      return;
    }
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refresh, liveMode]);

  const sessions = useMemo(
    () => groupSessions(traces, groupKey, wireFlows),
    [traces, groupKey, wireFlows],
  );

  useEffect(() => {
    onStatusRef.current?.({
      count: sessions.length,
      failed: sessionsFailed(sessions),
      disabled: debugEnabled === false,
    });
  }, [sessions, debugEnabled]);

  const selected: Session | undefined = useMemo(
    () => sessions.find((s) => s.key === selectedKey),
    [sessions, selectedKey],
  );
  const detail: Exchange | undefined = useMemo(
    () => selected?.exchanges.find((e) => e.seq === detailSeq),
    [selected, detailSeq],
  );
  const wireDetail = useMemo(
    () => selected?.exchanges.find((e) => e.seq === wireSeq)?.wire,
    [selected, wireSeq],
  );

  return (
    <section className="proxy-app" data-testid="sessions-panel">
      <div className="proxy-subheader">
        <span className="proxy-summary">{sessions.length} session(s)</span>
        <label className="proxy-filter-label">
          grouper par
          <select
            className="proxy-filter-input"
            value={groupKey}
            onChange={(e) => {
              setGroupKey(e.target.value as GroupKey);
              setSelectedKey(null);
              setExpandedSeq(null);
              setDetailSeq(null);
              setWireSeq(null);
            }}
          >
            <option value="run">run</option>
            <option value="agent">agent</option>
            <option value="agent_target">agent -&gt; target</option>
          </select>
        </label>
        <label className="proxy-filter-label">
          live
          <select
            className="proxy-filter-input"
            value={liveMode}
            onChange={(e) => setLiveMode(e.target.value as LiveMode)}
          >
            <option value="poll">poll (2s)</option>
            <option value="sse" disabled>
              sse (bientot)
            </option>
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
        <ul className="proxy-list" aria-label="sessions">
          {sessions.length === 0 && <li className="proxy-empty">aucune session</li>}
          {sessions.map((s) => (
            <li key={s.key}>
              <button
                type="button"
                className="proxy-list-item"
                data-active={s.key === selectedKey}
                data-outcome={s.failed > 0 ? "fail" : "ok"}
                onClick={() => {
                  setSelectedKey(s.key);
                  setExpandedSeq(null);
                  setDetailSeq(null);
                  setWireSeq(null);
                }}
              >
                <span className="proxy-badge" data-outcome={s.failed > 0 ? "fail" : "ok"}>
                  {s.total}
                </span>
                <span className="proxy-label">{s.label}</span>
                <span className="proxy-seq">
                  #{s.firstSeq}-{s.lastSeq}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div className="proxy-viewer">
          {selected === undefined ? (
            <div className="proxy-viewer-msg">selectionner une session a gauche</div>
          ) : (
            <ul className="proxy-list" aria-label="session exchanges">
              {selected.exchanges.map((ex) => (
                <li key={ex.seq}>
                  <button
                    type="button"
                    className="proxy-list-item"
                    data-active={ex.seq === expandedSeq}
                    data-outcome={ex.response.ok ? "ok" : "fail"}
                    onClick={() => setExpandedSeq(expandedSeq === ex.seq ? null : ex.seq)}
                  >
                    <span className="proxy-seq">#{ex.seq}</span>
                    <span className="proxy-badge" data-outcome={ex.response.ok ? "ok" : "fail"}>
                      {ex.response.status_code}
                    </span>
                    <span className="proxy-label">
                      {ex.intent.action_type} {ex.intent.resource}
                    </span>
                  </button>
                  {expandedSeq === ex.seq && (
                    <div className="proxy-exchange">
                      <pre className="proxy-exchange-side" data-testid="exchange-intent">
                        {JSON.stringify(ex.intent, null, 2)}
                      </pre>
                      <pre className="proxy-exchange-side" data-testid="exchange-response">
                        {JSON.stringify(ex.response, null, 2)}
                      </pre>
                      <button
                        type="button"
                        className="proxy-export"
                        onClick={() => setDetailSeq(ex.seq)}
                      >
                        JSON complet
                      </button>
                      {ex.wire && (
                        // Only shown when a wire flow matched (overlay on): opens
                        // the raw network bytes of this exchange in Monaco.
                        <button
                          type="button"
                          className="proxy-export"
                          data-testid="exchange-wire-btn"
                          onClick={() => setWireSeq(ex.seq)}
                        >
                          wire (octets)
                        </button>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {detail !== undefined && (
        <div className="proxy-viewer">
          <ViewerBoundary>
            <Suspense fallback={<div className="proxy-viewer-msg">loading editor...</div>}>
              <MonacoJsonViewer value={JSON.stringify(detail.raw, null, 2)} />
            </Suspense>
          </ViewerBoundary>
        </div>
      )}

      {wireDetail !== undefined && (
        <div className="proxy-viewer">
          <ViewerBoundary>
            <Suspense fallback={<div className="proxy-viewer-msg">loading editor...</div>}>
              <MonacoJsonViewer value={JSON.stringify(wireDetail, null, 2)} />
            </Suspense>
          </ViewerBoundary>
        </div>
      )}
    </section>
  );
}
