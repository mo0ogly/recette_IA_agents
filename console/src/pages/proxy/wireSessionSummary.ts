/**
 * wireSessionSummary — an autonomous instance's footprint per session.
 *
 * When the wire panel is pinned to one instance, its flows may span several
 * sessions (episodes). This pure helper groups those flows by session so the
 * console can show "this instance acted in N sessions" and let the operator
 * drill into any one — the visual form of the multi-session tracking the
 * platform records. Pure/deterministic (I4): a function of the flows only.
 */

import type { WireFlow } from "../../types/platform";
import { sessionId } from "./wireLayers";

/** One session an instance acted in: how many flows, how many failed, and the
 *  seq span (first..last) — enough to badge and order the sessions. */
export interface SessionFootprint {
  sessionId: string;
  count: number;
  fails: number;
  firstSeq: number;
  lastSeq: number;
}

/** Group flows by their session_id (flows without one are ignored), ordered by
 *  first appearance (firstSeq ascending) so the list reads chronologically. */
export function summarizeSessions(flows: WireFlow[]): SessionFootprint[] {
  const by = new Map<string, SessionFootprint>();
  for (const f of flows) {
    const sid = sessionId(f);
    if (!sid) continue;
    const cur = by.get(sid);
    if (cur === undefined) {
      by.set(sid, {
        sessionId: sid,
        count: 1,
        fails: f.ok ? 0 : 1,
        firstSeq: f.seq,
        lastSeq: f.seq,
      });
    } else {
      cur.count += 1;
      if (!f.ok) cur.fails += 1;
      cur.firstSeq = Math.min(cur.firstSeq, f.seq);
      cur.lastSeq = Math.max(cur.lastSeq, f.seq);
    }
  }
  return [...by.values()].sort((a, b) => a.firstSeq - b.firstSeq);
}
