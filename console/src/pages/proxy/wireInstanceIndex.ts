/**
 * wireInstanceIndex — the roster of autonomous instances seen in the capture.
 *
 * The orchestration "mesh" is otherwise dark: a run drives several agent
 * instances, each emitting wire flows tagged with its instance_id/session_id.
 * This pure helper rolls the buffered flows up per instance so the console can
 * list every instance that acted, with its session count, hosts it contacted
 * and failure tally — then deep-link into the packet list filtered to that
 * instance (instance -> its wire flows). This is the observability half of the
 * "connect orchestration to the cockpit" goal: it reads the capture, it never
 * drives a run.
 *
 * Pure/deterministic (I4): a function of the flows only, stable ordering.
 */

import type { WireFlow } from "../../types/platform";
import { instanceId, sessionId } from "./wireLayers";

export interface InstanceFootprint {
  instanceId: string;
  /** Distinct sessions this instance acted in. */
  sessions: number;
  /** Distinct target hosts this instance contacted, sorted. */
  hosts: string[];
  count: number;
  fails: number;
  firstSeq: number;
  lastSeq: number;
}

/** Group flows by instance_id (flows without one are ignored), ordered by first
 *  appearance (firstSeq ascending) so the roster reads chronologically. */
export function indexInstances(flows: WireFlow[]): InstanceFootprint[] {
  const by = new Map<
    string,
    InstanceFootprint & { _sessions: Set<string>; _hosts: Set<string> }
  >();
  for (const f of flows) {
    const iid = instanceId(f);
    if (!iid) continue;
    const sid = sessionId(f);
    let cur = by.get(iid);
    if (cur === undefined) {
      cur = {
        instanceId: iid,
        sessions: 0,
        hosts: [],
        count: 0,
        fails: 0,
        firstSeq: f.seq,
        lastSeq: f.seq,
        _sessions: new Set<string>(),
        _hosts: new Set<string>(),
      };
      by.set(iid, cur);
    }
    cur.count += 1;
    if (!f.ok) cur.fails += 1;
    cur.firstSeq = Math.min(cur.firstSeq, f.seq);
    cur.lastSeq = Math.max(cur.lastSeq, f.seq);
    if (sid) cur._sessions.add(sid);
    if (f.host) cur._hosts.add(f.host);
  }
  return [...by.values()]
    .sort((a, b) => a.firstSeq - b.firstSeq)
    .map((c) => ({
      instanceId: c.instanceId,
      sessions: c._sessions.size,
      hosts: [...c._hosts].sort(),
      count: c.count,
      fails: c.fails,
      firstSeq: c.firstSeq,
      lastSeq: c.lastSeq,
    }));
}
