/**
 * sessionModel -- pure, Monaco-free helpers that group proxy traces into
 * agent<->server SESSIONS for the Proxy console "sessions" source.
 *
 * Everything here is a pure function over ProxyTrace[] so it is unit-testable
 * without a DOM or the Monaco runtime, and deterministic (I4): stable sort by
 * the monotone `seq`, no clock, no random, no unordered Map iteration leaking
 * into the output order. Read-only by construction (I1/I5): a trace describes a
 * side effect that already happened; these helpers never mutate one.
 *
 * Concurrency: the backend ring is global with a shared monotone `seq`, so N
 * runs interleave. Grouping partitions by the chosen key with strict isolation
 * (no cross-contamination) and keeps each session's exchanges in seq order.
 */

import type { ProxyTrace } from "../../types/platform";

/** How exchanges are bucketed into a session. */
export type GroupKey = "run" | "agent" | "agent_target";

/** One agent<->server exchange, the readable req<->resp pair. */
export interface Exchange {
  seq: number;
  intent: { action_type: string; resource: string; payload: unknown };
  response: { status_code: number; ok: boolean; body: unknown };
  hash: string | null;
  /** The raw trace, kept for the "full JSON" Monaco detail. */
  raw: ProxyTrace;
}

/** A grouped session: an ordered run of exchanges sharing a key. */
export interface Session {
  key: string;
  label: string;
  agentId?: string;
  targets: string[];
  exchanges: Exchange[];
  total: number;
  failed: number;
  firstSeq: number;
  lastSeq: number;
}

/** Stable bucket value for a trace under a key. */
function keyOf(t: ProxyTrace, key: GroupKey): string {
  if (key === "agent") {
    return t.agent_id;
  }
  if (key === "agent_target") {
    return `${t.agent_id}|${t.target_system}`;
  }
  return t.run_id ?? "(no run)";
}

function toExchange(t: ProxyTrace): Exchange {
  return {
    seq: t.seq,
    intent: { action_type: t.action_type, resource: t.resource, payload: t.request_payload },
    response: { status_code: t.status_code, ok: t.ok, body: t.response },
    hash: t.side_effect_hash,
    raw: t,
  };
}

/**
 * Group traces into sessions by `key`. Sessions are ordered by `lastSeq` desc
 * (most-recently-active first), tie-break `firstSeq` asc then `key` asc, so the
 * order is total and deterministic. Each session's exchanges are sorted by seq.
 */
export function groupSessions(traces: ProxyTrace[], key: GroupKey): Session[] {
  const buckets = new Map<string, ProxyTrace[]>();
  for (const t of traces) {
    const k = keyOf(t, key);
    const list = buckets.get(k);
    if (list === undefined) {
      buckets.set(k, [t]);
    } else {
      list.push(t);
    }
  }

  const sessions: Session[] = [];
  for (const [k, list] of buckets) {
    const sorted = [...list].sort((a, b) => a.seq - b.seq);
    const exchanges = sorted.map(toExchange);
    const targets = [...new Set(sorted.map((t) => t.target_system))].sort();
    const agentIds = new Set(sorted.map((t) => t.agent_id));
    sessions.push({
      key: k,
      label: k,
      agentId: agentIds.size === 1 ? sorted[0].agent_id : undefined,
      targets,
      exchanges,
      total: exchanges.length,
      failed: exchanges.reduce((n, e) => (e.response.ok ? n : n + 1), 0),
      firstSeq: sorted[0].seq,
      lastSeq: sorted[sorted.length - 1].seq,
    });
  }

  sessions.sort(
    (a, b) => b.lastSeq - a.lastSeq || a.firstSeq - b.firstSeq || a.key.localeCompare(b.key),
  );
  return sessions;
}

/** Total failed exchanges across sessions (drives the menu badge). */
export function sessionsFailed(sessions: Session[]): number {
  return sessions.reduce((n, s) => n + s.failed, 0);
}
