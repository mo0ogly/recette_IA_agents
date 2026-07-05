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
 * Live: a 1s COALESCED delta poll (getProxySessionsDelta) replaces the old
 * four-calls-per-tick refresh: traces + wire flows + reconcile arrive in ONE
 * round trip, each side with its OWN cursor (last_seq / wire_last_seq) merged
 * through the pure mergeDelta with per-side reset semantics. useDeltaFeed does
 * not fit here (one feed, one cursor), so the two-cursor merge is written
 * inline, mirroring the hook's internals (busy guard, epoch guard, alive flag).
 * getRunEvents stays a separate fetch, issued only when a run is deep-linked.
 * The SSE mode is opt-in and wired in phase 2; the selector renders it
 * disabled until then.
 */

import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { getProxySessionsDelta, getRunEvents } from "../../api/client";
import type { ProxyTrace, WireFlow } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";
import { wireFlowToCurl } from "./curl";
import { type Decision, decisionForIndex, decisionsFromEvents } from "./decisionModel";
import {
  type Exchange,
  filterSessionsText,
  type GroupKey,
  groupSessions,
  type Session,
  sessionsFailed,
} from "./sessionModel";
import { mergeDelta } from "./useDeltaFeed";

const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));

const POLL_INTERVAL_MS = 1000;
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

export default function SessionsPanel({ onStatus, paused }: SourcePanelProps): JSX.Element {
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
  const [searchText, setSearchText] = useState("");
  // Hashes of wire flows the reconcile join flags as non-mediated (no matching
  // audit event = a ghost / shadow-AI path). Read-only overlay over the view.
  const [bypassHashes, setBypassHashes] = useState<Set<string>>(new Set());
  // DECIDE altitude: per-tool_call decisions of the preselected run, in order;
  // the i-th decision maps to the i-th governed exchange of the session.
  const [decisions, setDecisions] = useState<Decision[]>([]);

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

  // Two-cursor delta merge, mirroring useDeltaFeed's internals (busy guard,
  // epoch guard, alive flag) but coalesced: ONE response carries BOTH deltas
  // (traces via last_seq/reset, wire via wire_last_seq/wire_reset), so the
  // single-feed hook does not fit. Cursors live in refs so the interval
  // closure always reads the current value without re-arming the timer.
  const aliveRef = useRef(true);
  const busyRef = useRef(false);
  const traceSeqRef = useRef<number | null>(null);
  const wireSeqRef = useRef<number | null>(null);
  // Bumped on a feed restart (runParam change): a delta that was in flight
  // when the feed restarted is discarded instead of merging stale rows.
  const epochRef = useRef(0);

  const tick = useCallback(async (): Promise<void> => {
    if (busyRef.current) {
      return;
    }
    busyRef.current = true;
    const epoch = epochRef.current;
    try {
      const res = await getProxySessionsDelta({
        sinceSeq: traceSeqRef.current ?? undefined,
        wireSinceSeq: wireSeqRef.current ?? undefined,
        runId: runParam ?? undefined,
        strict: true,
      });
      if (!aliveRef.current || epoch !== epochRef.current) {
        return;
      }
      // Each side advances its OWN cursor and honors its OWN reset flag; a
      // stale cursor on one side never forces a resync of the other.
      traceSeqRef.current = res.last_seq;
      wireSeqRef.current = res.wire_last_seq;
      setTraces(
        (prev) =>
          mergeDelta(prev, { items: res.traces, last_seq: res.last_seq, reset: res.reset })
            .items,
      );
      setWireFlows(
        (prev) =>
          mergeDelta(prev, {
            items: res.wire_flows,
            last_seq: res.wire_last_seq,
            reset: res.wire_reset,
          }).items,
      );
      // Side channels of the coalesced envelope: the debug toggle state and
      // the strict wire<->audit join marking the ghost (non-mediated)
      // exchanges (same mapping as the old getReconcile call).
      setDebugEnabled(res.debug_enabled);
      setBypassHashes(
        new Set(
          res.reconcile.bypass_flows
            .map((f) => f.side_effect_hash)
            .filter((h): h is string => !!h),
        ),
      );
      setError(null);
      // DECIDE altitude (the agent's "why"): pull the run's ordered tool_call
      // decisions when a run is preselected. Separate fetch BY DESIGN (run
      // events are not proxy-owned); optional overlay -- a failure must never
      // blank the view (it only reads run frames, mutates nothing).
      if (runParam) {
        try {
          setDecisions(decisionsFromEvents(await getRunEvents(runParam)));
        } catch {
          setDecisions([]);
        }
      } else {
        setDecisions([]);
      }
    } catch (err: unknown) {
      if (aliveRef.current && epoch === epochRef.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      busyRef.current = false;
    }
  }, [runParam]);

  // Read `paused` from a ref inside the tick so toggling pause does NOT tear
  // down and re-run the effect (which would re-fire the initial fetch). The
  // initial fetch runs once on mount; only the recurring tick is gated.
  const pausedRef = useRef(paused);
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    aliveRef.current = true;
    // Full restart of BOTH cursors: `tick` changes identity only on a
    // runParam change, which re-scopes the wire delta + reconcile join
    // server-side, so the buffered rows and cursors are invalidated together.
    epochRef.current += 1;
    traceSeqRef.current = null;
    wireSeqRef.current = null;
    setTraces([]);
    setWireFlows([]);
    void tick();
    if (liveMode !== "poll") {
      return () => {
        aliveRef.current = false;
      };
    }
    const timer = setInterval(() => {
      if (!pausedRef.current) {
        void tick();
      }
    }, POLL_INTERVAL_MS);
    return () => {
      aliveRef.current = false;
      clearInterval(timer);
    };
  }, [tick, liveMode]);

  const sessions = useMemo(
    () => groupSessions(traces, groupKey, wireFlows),
    [traces, groupKey, wireFlows],
  );
  // Free-text narrowing: keep only sessions/exchanges matching the text. Drives
  // the list + selection so the timeline shows the matching exchanges only.
  const shownSessions = useMemo(
    () => filterSessionsText(sessions, searchText),
    [sessions, searchText],
  );

  useEffect(() => {
    onStatusRef.current?.({
      count: sessions.length,
      failed: sessionsFailed(sessions),
      disabled: debugEnabled === false,
    });
  }, [sessions, debugEnabled]);

  const selected: Session | undefined = useMemo(
    () => shownSessions.find((s) => s.key === selectedKey),
    [shownSessions, selectedKey],
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
        <span className="proxy-summary">{shownSessions.length} session(s)</span>
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
            <option value="poll">poll (1s)</option>
            <option value="sse" disabled>
              sse (bientot)
            </option>
          </select>
        </label>
        <label className="proxy-filter-label">
          recherche
          <input
            className="proxy-filter-input"
            type="search"
            data-testid="sessions-filter-text"
            placeholder="action / resource"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
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
          {shownSessions.length === 0 && <li className="proxy-empty">aucune session</li>}
          {shownSessions.map((s) => (
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
              {selected.exchanges.map((ex, idx) => {
                // Bind the optional wire to a const so the copy-curl handler
                // closure keeps the non-undefined narrowing (TS loses it inside
                // an onClick closure otherwise).
                const wire = ex.wire;
                // Three altitudes -- DECLARE (manifest target/cap on the trace)
                // / DECIDE (this: the agent's "why", the chosen tool + reasoning)
                // / DID (intent+response+wire below). The i-th exchange maps to
                // the i-th tool_call decision of the run, in order.
                const decision = decisionForIndex(decisions, idx);
                return (
                <li key={ex.seq}>
                  <button
                    type="button"
                    className="proxy-list-item"
                    data-active={ex.seq === expandedSeq}
                    data-outcome={ex.response.ok ? "ok" : "fail"}
                    onClick={() => {
                      setExpandedSeq(expandedSeq === ex.seq ? null : ex.seq);
                      setWireSeq(null);
                      setDetailSeq(null);
                    }}
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
                      {decision !== undefined && (
                        // DECIDE altitude: the agent's reasoning + chosen tool
                        // that drove this exchange (graceful: no decision -> no
                        // block).
                        <div className="proxy-decision" data-testid="exchange-decision">
                          decision: {decision.summary}
                        </div>
                      )}
                      {ex.hash !== null && bypassHashes.has(ex.hash) && (
                        // Reconcile flagged this exchange's side effect as having
                        // no matching audit event: a non-mediated (ghost) path.
                        <span
                          className="proxy-badge"
                          data-outcome="fail"
                          data-testid="exchange-ghost"
                        >
                          ghost / non-medie
                        </span>
                      )}
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
                      {wire && (
                        <button
                          type="button"
                          className="proxy-export"
                          data-testid="exchange-copy-curl"
                          onClick={() =>
                            void navigator.clipboard?.writeText(wireFlowToCurl(wire))
                          }
                        >
                          Copy curl
                        </button>
                      )}
                    </div>
                  )}
                </li>
                );
              })}
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
