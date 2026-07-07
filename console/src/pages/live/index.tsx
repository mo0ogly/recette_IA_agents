/**
 * Live Events page (G4) -- a realtime tail of governed events over SSE.
 *
 * Opens an EventSource on GET /events/stream and renders each event as it is
 * appended to the store (executed / denied / requested / resolved / error).
 *
 * Invariant note (I1): this is a DERIVED view, never the source of truth. A
 * dropped or missed event is still in the append-only audit log and is
 * recoverable via the Audit page -- a reconnect resumes the live tail, it does
 * not replay history. The transport status badge (GET /events/status) reflects
 * the Data Plane failure mode: a degraded NATS bus buffers and retries
 * (failure-modes.md); the Phase 1 in-process transport is never degraded.
 *
 * Contract notes (R16, captured against the real backend):
 * - The SSE `data:` payload is a StoredEvent envelope (seq, event_id, kind,
 *   payload, prev_hash, hash); see __fixtures__/liveEvent.fixture.json captured
 *   from a real /events/stream emission.
 * - payload.policy_decision is an object { verdict, policy_version, rule_id };
 *   the verdict badge reads its .verdict field.
 * - The EventSource factory and status fetcher are injectable so the contract
 *   test drives the component deterministically without a live socket.
 */

import { useEffect, useRef, useState } from "react";

import { getRealtimeStatus, realtimeStreamUrl } from "../../api/client";
import { StatusBadge } from "../../components/StatusBadge";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import type {
  ApprovalState,
  AuditEvent,
  AuditEventPayload,
  PolicyVerdict,
  RealtimeStatus,
} from "../../types/platform";
import "./live.css";

/** Minimal EventSource surface the page relies on (injectable for tests). */
export interface LiveSource {
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  close: () => void;
}

export type LiveSourceFactory = (url: string) => LiveSource;

export interface LivePageProps {
  /** EventSource factory; defaults to the browser EventSource. */
  sourceFactory?: LiveSourceFactory;
  /** Transport-health fetcher; defaults to GET /events/status. */
  statusFetcher?: () => Promise<RealtimeStatus>;
  /** Cap on retained events (newest first); older ones drop off the view. */
  maxEvents?: number;
  /** Status poll interval in ms. */
  statusIntervalMs?: number;
}

const DEFAULT_MAX_EVENTS = 200;
const DEFAULT_STATUS_INTERVAL_MS = 4000;
const HASH_DISPLAY_CHARS = 12;
const VERDICT_VALUES: readonly string[] = ["allow", "deny", "escalate"];
const APPROVAL_VALUES: readonly string[] = [
  "none",
  "pending",
  "approved",
  "denied",
  "timeout",
];

function defaultSourceFactory(url: string): LiveSource {
  // The browser EventSource matches LiveSource structurally; the cast keeps the
  // page decoupled from the DOM lib type so tests can inject a fake.
  return new EventSource(url) as unknown as LiveSource;
}

function extractVerdict(payload: AuditEventPayload): PolicyVerdict | null {
  const decision = payload.policy_decision;
  let candidate: unknown = null;
  if (typeof decision === "string") {
    candidate = decision;
  } else if (decision !== null && typeof decision === "object") {
    candidate = (decision as { verdict?: unknown }).verdict;
  }
  return typeof candidate === "string" && VERDICT_VALUES.includes(candidate)
    ? (candidate as PolicyVerdict)
    : null;
}

function extractApproval(payload: AuditEventPayload): ApprovalState | null {
  const value = payload.approval_state;
  return typeof value === "string" && APPROVAL_VALUES.includes(value)
    ? (value as ApprovalState)
    : null;
}

function targetAction(payload: AuditEventPayload): string {
  const target = payload.target_system ?? null;
  const action = payload.action_type ?? null;
  if (target !== null && action !== null) {
    return `${target}/${action}`;
  }
  return target ?? action ?? "";
}

export default function LivePage(props: LivePageProps): JSX.Element {
  const {
    sourceFactory = defaultSourceFactory,
    statusFetcher = getRealtimeStatus,
    maxEvents = DEFAULT_MAX_EVENTS,
    statusIntervalMs = DEFAULT_STATUS_INTERVAL_MS,
  } = props;

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [connected, setConnected] = useState<boolean>(false);
  const [status, setStatus] = useState<RealtimeStatus | null>(null);
  const seenSeq = useRef<Set<number>>(new Set());

  useEffect(() => {
    const source = sourceFactory(realtimeStreamUrl());
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (message) => {
      let event: AuditEvent;
      try {
        event = JSON.parse(message.data) as AuditEvent;
      } catch {
        // A malformed frame on the wire must never crash the live view.
        return;
      }
      // De-duplicate by seq: a reconnect can re-deliver the boundary event.
      if (seenSeq.current.has(event.seq)) {
        return;
      }
      seenSeq.current.add(event.seq);
      setEvents((prev) => [event, ...prev].slice(0, maxEvents));
    };
    return () => source.close();
  }, [sourceFactory, maxEvents]);

  useEffect(() => {
    let alive = true;
    const poll = (): void => {
      statusFetcher()
        .then((next) => {
          if (alive) {
            setStatus(next);
          }
        })
        .catch(() => {
          // Status is advisory; a failed probe leaves the last known value.
        });
    };
    poll();
    const timer = setInterval(poll, statusIntervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [statusFetcher, statusIntervalMs]);

  return (
    <section>
      <div className="page-head">
        <h1>Flux temps reel</h1>
        <PageHelp topic="live" />
        <AssistButton topic="audit.recent" label="Evenements temps reel" />
      </div>

      <div className="live-toolbar">
        <span
          className={connected ? "live-badge live-badge-on" : "live-badge live-badge-off"}
          role="status"
          data-testid="live-connection"
        >
          {connected ? "Connecte" : "Deconnecte"}
        </span>
        {status !== null && status.degraded && (
          <span className="live-badge live-badge-degraded" role="alert">
            Bus degrade
          </span>
        )}
        {status !== null && (
          <span className="live-meta">
            En attente: {status.pending} - Abandonnes: {status.dropped}
          </span>
        )}
        <span className="live-meta">{events.length} evenement(s)</span>
      </div>

      <p className="live-note">
        Vue derivee du journal (I1) : l'historique complet est dans l'onglet
        Audit. Une reconnexion reprend le tail courant, elle ne rejoue pas le
        passe.
      </p>

      {events.length === 0 ? (
        <p className="live-empty" data-testid="live-empty">
          En attente d'evenements gouvernes...
        </p>
      ) : (
        <table className="live-table">
          <thead>
            <tr>
              <th>Seq</th>
              <th>Type</th>
              <th>Agent</th>
              <th>Cible / Action</th>
              <th>Verdict</th>
              <th>Approbation</th>
              <th>Risque</th>
              <th>Event ID</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => {
              const verdict = extractVerdict(event.payload);
              const approval = extractApproval(event.payload);
              return (
                <tr key={event.seq} className="live-row" data-testid="live-row">
                  <td>{event.seq}</td>
                  <td>{event.kind}</td>
                  <td>{event.payload.agent_id ?? "-"}</td>
                  <td className="live-subtle">{targetAction(event.payload)}</td>
                  <td>
                    {verdict !== null ? (
                      <StatusBadge kind="verdict" value={verdict} />
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>
                    {approval !== null ? (
                      <StatusBadge kind="approval" value={approval} />
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>{event.payload.risk_level ?? "-"}</td>
                  <td className="mono" title={event.event_id}>
                    {event.event_id.slice(0, HASH_DISPLAY_CHARS)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
