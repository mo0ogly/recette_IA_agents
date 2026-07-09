/**
 * wireStats — conversation statistics over captured agent flows (defensive).
 *
 * The Wireshark "Statistics" menu equivalent for agent traffic: protocol
 * hierarchy (which dissected layers are present), endpoint hierarchy (top hosts),
 * and a token/cost accounting rolled up per autonomous instance. Pure aggregation
 * over already-captured flows — no I/O, no generation, no attack logic; it only
 * COUNTS and SUMS what crossed the wire. Deterministic (I4): sorted outputs, no
 * clock, no randomness.
 */

import type { WireFlow } from "../../types/platform";
import { instanceId, readLayers } from "./wireLayers";
import { decodeLlmFlow } from "./wireLlmDecode";

/** Share of flows that carry a given dissected layer. */
export interface ProtocolStat {
  layer: string;
  flows: number;
  share: number; // 0..1
}

/** Per-host footprint. */
export interface EndpointStat {
  host: string;
  flows: number;
  fails: number;
}

/** Token accounting rolled up under one instance (or "-" when unattributed). */
export interface TokenStat {
  instance: string;
  model: string | null;
  flows: number;
  input: number;
  output: number;
}

export interface WireStats {
  totalFlows: number;
  fails: number;
  protocols: ProtocolStat[];
  endpoints: EndpointStat[];
  tokensByInstance: TokenStat[];
  tokensTotal: { input: number; output: number };
}

const _EMPTY: WireStats = {
  totalFlows: 0,
  fails: 0,
  protocols: [],
  endpoints: [],
  tokensByInstance: [],
  tokensTotal: { input: 0, output: 0 },
};

function _protocols(flows: WireFlow[]): ProtocolStat[] {
  const total = flows.length;
  const counts: Record<string, number> = { l3l4: 0, tls: 0, http: 0, timing: 0, l8: 0 };
  for (const flow of flows) {
    const l = readLayers(flow);
    if (l?.l3l4) counts.l3l4 += 1;
    if (l?.tls) counts.tls += 1;
    if (l?.http) counts.http += 1;
    if (l?.timing) counts.timing += 1;
    if (decodeLlmFlow(flow) !== null) counts.l8 += 1;
  }
  // Fixed layer order (network stack, bottom-up) -> deterministic.
  return ["l3l4", "tls", "http", "l8", "timing"].map((layer) => ({
    layer,
    flows: counts[layer],
    share: total > 0 ? counts[layer] / total : 0,
  }));
}

function _endpoints(flows: WireFlow[]): EndpointStat[] {
  const by = new Map<string, EndpointStat>();
  for (const flow of flows) {
    const host = flow.host || "(unknown)";
    const cur = by.get(host);
    if (cur === undefined) {
      by.set(host, { host, flows: 1, fails: flow.ok ? 0 : 1 });
    } else {
      cur.flows += 1;
      if (!flow.ok) cur.fails += 1;
    }
  }
  // Most-active host first; ties broken by host name for stable order.
  return [...by.values()].sort((a, b) => b.flows - a.flows || a.host.localeCompare(b.host));
}

function _tokens(flows: WireFlow[]): { rows: TokenStat[]; total: { input: number; output: number } } {
  const by = new Map<string, TokenStat>();
  let ti = 0;
  let to = 0;
  for (const flow of flows) {
    const l8 = decodeLlmFlow(flow);
    if (l8 === null) continue;
    const inTok = l8.usage?.input ?? 0;
    const outTok = l8.usage?.output ?? 0;
    ti += inTok;
    to += outTok;
    const key = instanceId(flow) ?? "-";
    const cur = by.get(key);
    if (cur === undefined) {
      by.set(key, { instance: key, model: l8.model, flows: 1, input: inTok, output: outTok });
    } else {
      cur.flows += 1;
      cur.input += inTok;
      cur.output += outTok;
      if (cur.model === null) cur.model = l8.model;
    }
  }
  const rows = [...by.values()].sort(
    (a, b) => b.input + b.output - (a.input + a.output) || a.instance.localeCompare(b.instance),
  );
  return { rows, total: { input: ti, output: to } };
}

/** Aggregate statistics over the given flows (pure, deterministic). */
export function computeWireStats(flows: WireFlow[]): WireStats {
  if (flows.length === 0) return _EMPTY;
  const { rows, total } = _tokens(flows);
  return {
    totalFlows: flows.length,
    fails: flows.reduce((n, f) => (f.ok ? n : n + 1), 0),
    protocols: _protocols(flows),
    endpoints: _endpoints(flows),
    tokensByInstance: rows,
    tokensTotal: total,
  };
}
