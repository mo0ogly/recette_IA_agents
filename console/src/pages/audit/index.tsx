/**
 * Audit Trail page -- read-only viewer over the append-only event store (I1).
 *
 * Shows the hash-chain verification status (GET /audit/verify), the event log
 * (GET /audit/events) with kind / agent_id / target_system filters, and a
 * per-event expandable payload view.
 *
 * Contract notes (R16, captured against the real backend):
 * - The backend wraps the event list in an { events: [...] } envelope while
 *   the client is typed as a bare array; unwrapEvents normalizes both shapes
 *   so the page works against the real payload.
 * - payload.policy_decision is an object { verdict, policy_version, rule_id };
 *   the verdict badge reads its .verdict field (a bare string is also accepted).
 * - target_system is not part of AuditEventsParams on the client, so that
 *   filter is applied client-side on payload.target_system.
 */

import { Fragment, useCallback, useEffect, useState } from "react";

import type { AuditEventsParams } from "../../api/client";
import { listAuditEvents, verifyChain } from "../../api/client";
import { StatusBadge } from "../../components/StatusBadge";
import type {
  ApprovalState,
  ChainReport,
  PolicyVerdict,
  StoredEvent,
} from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import "./audit.css";

/** Event kinds offered by the kind filter (plus the "all" pseudo-value). */
const EVENT_KINDS = [
  "action_requested",
  "action_executed",
  "action_denied",
  "approval_resolved",
  "platform_error",
] as const;

const VERDICT_VALUES: readonly string[] = ["allow", "deny", "escalate"];

const APPROVAL_VALUES: readonly string[] = [
  "none",
  "pending",
  "approved",
  "denied",
  "timeout",
];

/** Number of leading characters shown for event ids and hashes. */
const HASH_DISPLAY_CHARS = 12;

/**
 * Normalize the audit events response: the backend returns
 * { events: [...] } while the client type declares StoredEvent[].
 */
function unwrapEvents(raw: unknown): StoredEvent[] {
  if (Array.isArray(raw)) {
    return raw as StoredEvent[];
  }
  if (raw !== null && typeof raw === "object") {
    const inner = (raw as { events?: unknown }).events;
    if (Array.isArray(inner)) {
      return inner as StoredEvent[];
    }
  }
  return [];
}

/** Read a string field from an event payload, or null when absent. */
function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

/**
 * Extract the policy verdict from payload.policy_decision, which is an
 * object { verdict, policy_version, rule_id } in the real contract
 * (a bare string verdict is tolerated for forward compatibility).
 */
function extractVerdict(payload: Record<string, unknown>): PolicyVerdict | null {
  const decision = payload["policy_decision"];
  let candidate: unknown = null;
  if (typeof decision === "string") {
    candidate = decision;
  } else if (decision !== null && typeof decision === "object") {
    candidate = (decision as { verdict?: unknown }).verdict;
  }
  if (typeof candidate === "string" && VERDICT_VALUES.includes(candidate)) {
    return candidate as PolicyVerdict;
  }
  return null;
}

/** Extract a valid approval_state from the payload, or null when absent. */
function extractApprovalState(payload: Record<string, unknown>): ApprovalState | null {
  const value = payload["approval_state"];
  if (typeof value === "string" && APPROVAL_VALUES.includes(value)) {
    return value as ApprovalState;
  }
  return null;
}

function truncateId(value: string): string {
  return value.length > HASH_DISPLAY_CHARS
    ? `${value.slice(0, HASH_DISPLAY_CHARS)}...`
    : value;
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

export default function AuditPage(): JSX.Element {
  const [chain, setChain] = useState<ChainReport | null>(null);
  const [chainError, setChainError] = useState<string | null>(null);
  const [events, setEvents] = useState<StoredEvent[]>([]);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [expandedSeq, setExpandedSeq] = useState<number | null>(null);

  const [kindFilter, setKindFilter] = useState<string>("all");
  const [agentFilter, setAgentFilter] = useState<string>("");
  const [targetFilter, setTargetFilter] = useState<string>("");

  const load = useCallback(
    async (kind: string, agentId: string, targetSystem: string): Promise<void> => {
      setLoading(true);
      const params: AuditEventsParams = {};
      if (kind !== "all") {
        params.kind = kind;
      }
      if (agentId.length > 0) {
        params.agent_id = agentId;
      }
      // Failures are isolated: a broken verify call still leaves the event
      // table usable, and vice versa. Each failure gets its own banner.
      const [chainResult, eventsResult] = await Promise.allSettled([
        verifyChain(),
        listAuditEvents(params),
      ]);
      if (chainResult.status === "fulfilled") {
        setChain(chainResult.value);
        setChainError(null);
      } else {
        setChain(null);
        setChainError(errorMessage(chainResult.reason));
      }
      if (eventsResult.status === "fulfilled") {
        let next = unwrapEvents(eventsResult.value);
        if (targetSystem.length > 0) {
          next = next.filter(
            (event) => payloadString(event.payload, "target_system") === targetSystem,
          );
        }
        setEvents(next);
        setEventsError(null);
      } else {
        setEvents([]);
        setEventsError(errorMessage(eventsResult.reason));
      }
      setExpandedSeq(null);
      setLoading(false);
    },
    [],
  );

  useEffect(() => {
    void load("all", "", "");
  }, [load]);

  function handleApply(submitEvent: React.FormEvent<HTMLFormElement>): void {
    submitEvent.preventDefault();
    void load(kindFilter, agentFilter.trim(), targetFilter.trim());
  }

  return (
    <section>
      <div className="page-head">
        <h1>Audit Trail</h1>
        <PageHelp topic="audit" />
      </div>

      {chain !== null && chain.ok && (
        <div className="banner banner-ok" role="status">
          Chain intact ({chain.checked} events verified)
        </div>
      )}
      {chain !== null && !chain.ok && (
        <div className="banner banner-broken" role="alert">
          Chain broken at seq {chain.first_break_seq ?? "unknown"}:{" "}
          {chain.detail ?? "no detail provided"}
        </div>
      )}
      {chainError !== null && (
        <div className="banner banner-broken" role="alert">
          Chain verification failed: {chainError}
        </div>
      )}
      {eventsError !== null && (
        <div className="banner banner-broken" role="alert">
          Failed to load audit events: {eventsError}
        </div>
      )}

      <form className="audit-filters" onSubmit={handleApply}>
        <div className="audit-filter-field">
          <label htmlFor="audit-filter-kind">Kind</label>
          <select
            id="audit-filter-kind"
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
          >
            <option value="all">all</option>
            {EVENT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
        </div>
        <div className="audit-filter-field">
          <label htmlFor="audit-filter-agent">Agent ID</label>
          <input
            id="audit-filter-agent"
            type="text"
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            placeholder="agent-admin"
          />
        </div>
        <div className="audit-filter-field">
          <label htmlFor="audit-filter-target">Target system</label>
          <input
            id="audit-filter-target"
            type="text"
            value={targetFilter}
            onChange={(e) => setTargetFilter(e.target.value)}
            placeholder="okta"
          />
        </div>
        <button type="submit">Apply</button>
      </form>

      {loading && <p>Loading audit log...</p>}

      {!loading && events.length === 0 && eventsError === null && (
        <p className="audit-empty">No audit events match the current filters.</p>
      )}

      {!loading && events.length > 0 && (
        <table className="audit-table">
          <thead>
            <tr>
              <th>Seq</th>
              <th>Kind</th>
              <th>Event ID</th>
              <th>Agent</th>
              <th>Verdict</th>
              <th>Approval</th>
              <th>Hash</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => {
              const verdict = extractVerdict(event.payload);
              const approval = extractApprovalState(event.payload);
              const agentId = payloadString(event.payload, "agent_id");
              const targetSystem = payloadString(event.payload, "target_system");
              const actionType = payloadString(event.payload, "action_type");
              const expanded = expandedSeq === event.seq;
              return (
                <Fragment key={event.seq}>
                  <tr
                    className="audit-row"
                    onClick={() => setExpandedSeq(expanded ? null : event.seq)}
                  >
                    <td>{event.seq}</td>
                    <td>{event.kind}</td>
                    <td className="mono" title={event.event_id}>
                      {truncateId(event.event_id)}
                    </td>
                    <td>
                      <div>{agentId ?? "-"}</div>
                      <div className="audit-subtle">
                        {targetSystem !== null && actionType !== null
                          ? `${targetSystem}/${actionType}`
                          : targetSystem ?? actionType ?? ""}
                      </div>
                    </td>
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
                    <td className="mono">{event.hash.slice(0, HASH_DISPLAY_CHARS)}</td>
                  </tr>
                  {expanded && (
                    <tr className="audit-detail-row">
                      <td colSpan={7}>
                        <pre className="audit-payload">
                          {JSON.stringify(event.payload, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
