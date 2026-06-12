/**
 * Approval Inbox page (I6 console side).
 *
 * Lists actions blocked on human approval (GET /approvals?state=pending) and
 * lets an operator approve or deny each one. A resolution returns the final
 * ActionOutcome, rendered inline (approval badge, executed flag, truncated
 * side_effect_hash) while the item leaves the pending list. The sweep button
 * resolves expired approvals to the timeout state server-side.
 *
 * R16 contract note: the backend wraps the inbox in a { pending: [...] }
 * envelope (see __fixtures__/pending.fixture.json, captured from the live
 * API). The shared client types the call as PendingApproval[], so this page
 * unwraps the envelope explicitly here -- client.ts is outside this
 * workstream's ownership.
 */

import { useCallback, useEffect, useState } from "react";
import {
  approveAction,
  denyAction,
  listPendingApprovals,
  sweepTimeouts,
} from "../../api/client";
import type {
  ActionOutcome,
  PendingApproval,
  RiskLevel,
} from "../../types/platform";
import { StatusBadge } from "../../components/StatusBadge";
import "./approvals.css";

const RISK_LEVELS: readonly RiskLevel[] = ["low", "medium", "high", "critical"];

function isRiskLevel(value: string): value is RiskLevel {
  return (RISK_LEVELS as readonly string[]).includes(value);
}

/**
 * Unwraps the real /approvals?state=pending payload. The captured fixture
 * shows a { pending: PendingApproval[] } envelope; a bare array is also
 * accepted so a future client-side unwrap does not break this page.
 */
function unwrapPending(raw: unknown): PendingApproval[] {
  if (Array.isArray(raw)) {
    return raw as PendingApproval[];
  }
  if (raw !== null && typeof raw === "object" && Array.isArray((raw as { pending?: unknown }).pending)) {
    return (raw as { pending: PendingApproval[] }).pending;
  }
  return [];
}

/** Extracts the timed-out event ids from the sweep response. */
function unwrapTimedOut(raw: { timed_out?: unknown }): string[] {
  const value = raw.timed_out;
  return Array.isArray(value) ? value.map(String) : [];
}

function truncateHash(hash: string): string {
  return hash.length > 12 ? `${hash.slice(0, 12)}...` : hash;
}

/** A pending item resolved during this session, with its final outcome. */
interface ResolvedItem {
  item: PendingApproval;
  outcome: ActionOutcome;
}

interface PendingCardProps {
  item: PendingApproval;
  approver: string;
  busy: boolean;
  onApprove: (item: PendingApproval) => void;
  onDeny: (item: PendingApproval, reason: string) => void;
}

function PendingCard({ item, approver, busy, onApprove, onDeny }: PendingCardProps): JSX.Element {
  const [reason, setReason] = useState("");
  const approverMissing = approver.trim().length === 0;

  return (
    <div className="approval-card" data-testid={`pending-${item.event_id}`}>
      <div className="approval-card-header">
        <span className="approval-agent">{item.agent_id}</span>
        <span className="approval-role">{item.role}</span>
        {isRiskLevel(item.risk_level) ? (
          <StatusBadge kind="risk" value={item.risk_level} />
        ) : (
          <span className="badge">{item.risk_level}</span>
        )}
      </div>
      <div className="approval-meta">
        <span>
          <strong>{item.target_system}</strong> / {item.action_type}
        </span>
        <span>
          resource: <strong>{item.resource}</strong>
        </span>
        <span>requested at: {item.requested_at}</span>
        <span>policy: {item.policy_version}</span>
      </div>
      <div className="approval-actions">
        <button
          type="button"
          className="btn btn-approve"
          disabled={busy || approverMissing}
          onClick={() => onApprove(item)}
        >
          Approve
        </button>
        <input
          type="text"
          placeholder="Deny reason (required to deny)"
          aria-label={`Deny reason for ${item.event_id}`}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <button
          type="button"
          className="btn btn-deny"
          disabled={busy || approverMissing || reason.trim().length === 0}
          onClick={() => onDeny(item, reason.trim())}
        >
          Deny
        </button>
      </div>
    </div>
  );
}

function ResolvedCard({ item, outcome }: ResolvedItem): JSX.Element {
  return (
    <div className="approval-card" data-testid={`resolved-${outcome.event_id}`}>
      <div className="approval-card-header">
        <span className="approval-agent">{item.agent_id}</span>
        <span className="approval-role">
          {item.target_system} / {item.action_type} on {item.resource}
        </span>
      </div>
      <div className="outcome-line">
        <StatusBadge kind="approval" value={outcome.approval_state} />
        <span>executed: {outcome.executed ? "yes" : "no"}</span>
        {outcome.side_effect_hash !== null && outcome.side_effect_hash !== undefined ? (
          <span>
            side effect hash:{" "}
            <span className="mono" title={outcome.side_effect_hash}>
              {truncateHash(outcome.side_effect_hash)}
            </span>
          </span>
        ) : null}
        {outcome.policy_version !== null ? <span>policy: {outcome.policy_version}</span> : null}
      </div>
    </div>
  );
}

export default function ApprovalsPage(): JSX.Element {
  const [pending, setPending] = useState<PendingApproval[]>([]);
  const [resolved, setResolved] = useState<ResolvedItem[]>([]);
  const [approver, setApprover] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [timedOut, setTimedOut] = useState<string[] | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const raw = await listPendingApprovals();
      setPending(unwrapPending(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleResolved = useCallback((item: PendingApproval, outcome: ActionOutcome) => {
    setPending((prev) => prev.filter((p) => p.event_id !== item.event_id));
    setResolved((prev) => [...prev, { item, outcome }]);
  }, []);

  const handleApprove = useCallback(
    async (item: PendingApproval) => {
      setBusy(true);
      setError(null);
      try {
        const outcome = await approveAction(item.event_id, approver.trim());
        handleResolved(item, outcome);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [approver, handleResolved],
  );

  const handleDeny = useCallback(
    async (item: PendingApproval, reason: string) => {
      setBusy(true);
      setError(null);
      try {
        const outcome = await denyAction(item.event_id, approver.trim(), reason);
        handleResolved(item, outcome);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [approver, handleResolved],
  );

  const handleSweep = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const raw = await sweepTimeouts();
      setTimedOut(unwrapTimedOut(raw));
      // Timed-out items are no longer pending: refresh the inbox.
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  return (
    <div>
      <h1>Approval Inbox</h1>

      {error !== null ? (
        <div className="approvals-error" role="alert">
          {error}
        </div>
      ) : null}

      <div className="approvals-toolbar">
        <div className="approvals-field">
          <label htmlFor="approver-input">Approver</label>
          <input
            id="approver-input"
            type="text"
            placeholder="user:rssi"
            value={approver}
            onChange={(e) => setApprover(e.target.value)}
          />
        </div>
        <button type="button" className="btn" disabled={busy} onClick={() => void handleSweep()}>
          Sweep timeouts
        </button>
        <button type="button" className="btn" disabled={busy || loading} onClick={() => void refresh()}>
          Refresh
        </button>
      </div>

      {timedOut !== null ? (
        <p className="approvals-sweep-result">
          Sweep result: {timedOut.length} timed out
          {timedOut.length > 0 ? ` (${timedOut.join(", ")})` : ""}
        </p>
      ) : null}

      {loading ? (
        <p className="approvals-empty">Loading pending approvals...</p>
      ) : pending.length === 0 ? (
        <p className="approvals-empty">No pending approvals.</p>
      ) : (
        pending.map((item) => (
          <PendingCard
            key={item.event_id}
            item={item}
            approver={approver}
            busy={busy}
            onApprove={(it) => void handleApprove(it)}
            onDeny={(it, reason) => void handleDeny(it, reason)}
          />
        ))
      )}

      {resolved.length > 0 ? (
        <>
          <h2 className="approvals-section-title">Resolved this session</h2>
          {resolved.map((r) => (
            <ResolvedCard key={r.outcome.event_id} item={r.item} outcome={r.outcome} />
          ))}
        </>
      ) : null}
    </div>
  );
}
