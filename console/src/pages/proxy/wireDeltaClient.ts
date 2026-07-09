/**
 * wireDeltaClient — wire delta poll WITH multi-session tracking filters.
 *
 * The base `getWireFlowsDelta` (api/client.ts) maps a fixed param set and cannot
 * be extended there (that file is at its size ceiling). This thin wrapper reuses
 * the exported `request` transport and adds `session_id`/`instance_id` to the
 * query, so filtering by autonomous instance and session happens SERVER-SIDE
 * (over the whole store, not just the buffered rows). Same envelope/`reset`
 * semantics as the base delta — the panel consumes it identically.
 */

import { request } from "../../api/client";
import type { WireFlowResponse } from "../../types/platform";

/** Server-side selection for the /proxy/wire delta poll, tracking-aware.
 *  camelCase here, mapped to snake_case query params below. All optional. */
export interface WireDeltaTrackedQuery {
  tail?: number;
  runId?: string;
  sinceSeq?: number;
  host?: string;
  method?: string;
  status?: number;
  /** Session (one conversation/episode) exact match. */
  sessionId?: string;
  /** Autonomous instance exact match — follows it across the sessions it acted in. */
  instanceId?: string;
  q?: string;
  limit?: number;
}

/** Build `?a=b&...` from camel/snake params, omitting undefined and "" values.
 *  `sinceSeq === 0` (a valid genesis cursor) is kept; only undefined is dropped. */
function queryString(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    sp.set(key, String(value));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** Delta-poll of intercepted wire flows with the tracking filters applied. */
export function getWireFlowsDeltaTracked(p: WireDeltaTrackedQuery): Promise<WireFlowResponse> {
  const path =
    "/proxy/wire" +
    queryString({
      tail: p.tail,
      run_id: p.runId,
      since_seq: p.sinceSeq,
      host: p.host,
      method: p.method,
      status: p.status,
      session_id: p.sessionId,
      instance_id: p.instanceId,
      q: p.q,
      limit: p.limit,
    });
  return request<WireFlowResponse>(path, { method: "GET" });
}
