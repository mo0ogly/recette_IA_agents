/**
 * wireLayers — the per-layer network decode carried by a WireFlow.
 *
 * The backend emits a nested `layers` object on each wire flow (L3/L4, TLS,
 * HTTP headers, per-phase timing) captured by the mitmproxy addon from the
 * sockets + TLS handshake. These types live here (not in types/platform.ts,
 * which is already at its size ceiling) and are read off a flow through the
 * `readLayers` accessor so WirePanel can render a legible layer stack.
 *
 * Every field is nullable by design: a value the addon could not extract for a
 * given flow is `null` (honest absence), never faked — mirroring the "pas de
 * mock" contract on the capture side.
 */

import type { WireFlow } from "../../types/platform";

/** L3/L4 transport endpoints (real IPs/ports from the sockets). */
export interface WireL3L4 {
  src_ip: string | null;
  src_port: number | null;
  dst_ip: string | null;
  dst_port: number | null;
  transport: string;
  ip_version: number | null;
}

/** Negotiated TLS parameters + upstream certificate + the client JA3. */
export interface WireTls {
  version: string | null;
  cipher: string | null;
  sni: string | null;
  alpn: string | null;
  upstream_version?: string | null;
  upstream_cipher?: string | null;
  /** JA3 MD5 of the agent's ClientHello — the signal a network discovery probe
   *  fingerprints on. Null when the handshake could not be parsed. */
  ja3: string | null;
  ja3_string: string | null;
  cert_subject?: string | null;
  cert_issuer?: string | null;
  cert_not_after?: string | null;
}

/** L7 HTTP metadata beyond the bodies (secrets masked at the source). */
export interface WireHttp {
  version: string | null;
  reason: string | null;
  request_headers: Record<string, string>;
  response_headers: Record<string, string>;
}

/** Per-phase timing waterfall (ms); each phase null when unmeasured. */
export interface WireTiming {
  tcp_setup_ms: number | null;
  tls_setup_ms: number | null;
  ttfb_ms: number | null;
  total_ms: number | null;
}

/** The nested decode; any layer may be absent (e.g. `tls` on plain HTTP). */
export interface WireLayers {
  l3l4?: WireL3L4 | null;
  tls?: WireTls | null;
  http?: WireHttp | null;
  timing?: WireTiming | null;
}

/** A WireFlow that may carry the `layers` decode (server-provided, optional). */
export type WireFlowWithLayers = WireFlow & { layers?: WireLayers | null };

/** A WireFlow that may carry multi-session tracking identity (server-provided).
 *  `session_id` = one conversation/episode; `instance_id` = the autonomous agent
 *  instance that emitted the flow (anchored on its agent passport). Null on legacy
 *  rows / unattributed flows. Lets the console follow one instance across sessions. */
export type WireFlowTracked = WireFlow & {
  session_id?: string | null;
  instance_id?: string | null;
};

/** The session (conversation/episode) that emitted this flow, or null. */
export function sessionId(flow: WireFlow): string | null {
  const v = (flow as WireFlowTracked).session_id;
  return v ? String(v) : null;
}

/** The autonomous agent instance that emitted this flow, or null. */
export function instanceId(flow: WireFlow): string | null {
  const v = (flow as WireFlowTracked).instance_id;
  return v ? String(v) : null;
}

/** Read the per-layer decode off a flow, or null when absent (legacy rows). */
export function readLayers(flow: WireFlow): WireLayers | null {
  const layers = (flow as WireFlowWithLayers).layers;
  return layers && typeof layers === "object" ? layers : null;
}

/** True when at least one layer is present (drives the "réseau" section). */
export function hasLayers(flow: WireFlow): boolean {
  const l = readLayers(flow);
  return l !== null && Boolean(l.l3l4 || l.tls || l.http || l.timing);
}

/** Format an "ip:port" endpoint, or "-" when unknown. Pure display helper. */
export function endpoint(ip: string | null | undefined, port: number | null | undefined): string {
  if (!ip && port == null) return "-";
  return `${ip ?? "?"}:${port ?? "?"}`;
}
