/**
 * wireFields — the addressable field registry for the display-filter engine.
 *
 * Wireshark exposes every dissected value under a dotted name (`http.status`,
 * `tls.handshake.type`). This module does the same for a captured agent flow: it
 * projects the layered decode (L3/L4, TLS/JA3, HTTP, timing) and the L8 semantic
 * dissector (`decodeLlmFlow`) plus the tracking identity into a flat map of
 * `path -> extractor`. The display-filter DSL (wireFilter.ts) resolves field
 * paths through this registry; the panel uses the field LIST for autocomplete.
 *
 * Pure and read-only (I1/I4): every extractor is a pure function of the flow;
 * nothing here mutates a flow or performs I/O. Per-flow decodes (layers, L8) are
 * memoised in WeakMaps so a filter touching several l8.* fields decodes once.
 */

import type { WireFlow } from "../../types/platform";
import { instanceId, readLayers, sessionId, type WireLayers } from "./wireLayers";
import { decodeLlmFlow, type LlmExchange } from "./wireLlmDecode";

export type FieldValue = string | number | null;

/** A dissected, addressable field. ``multi`` marks a repeated value (e.g. the
 *  tools a model invoked): a comparison matches when ANY element matches. */
export interface WireField {
  path: string;
  type: "string" | "number";
  multi?: boolean;
  desc: string;
  get: (flow: WireFlow) => FieldValue | FieldValue[];
}

const _layerCache = new WeakMap<WireFlow, WireLayers | null>();
const _l8Cache = new WeakMap<WireFlow, LlmExchange | null>();

function layers(flow: WireFlow): WireLayers | null {
  if (!_layerCache.has(flow)) _layerCache.set(flow, readLayers(flow));
  return _layerCache.get(flow) ?? null;
}

function l8(flow: WireFlow): LlmExchange | null {
  if (!_l8Cache.has(flow)) _l8Cache.set(flow, decodeLlmFlow(flow));
  return _l8Cache.get(flow) ?? null;
}

function f(
  path: string,
  type: "string" | "number",
  desc: string,
  get: (flow: WireFlow) => FieldValue | FieldValue[],
  multi = false,
): WireField {
  return { path, type, desc, get, multi };
}

/** The ordered field catalogue (drives autocomplete + docs). */
export const WIRE_FIELD_LIST: WireField[] = [
  // Top level + tracking identity
  f("host", "string", "Target host", (fl) => fl.host || null),
  f("method", "string", "HTTP method", (fl) => fl.method || null),
  f("path", "string", "Request path", (fl) => fl.path || null),
  f("status", "number", "HTTP status code", (fl) => fl.status_code),
  f("session", "string", "Session (conversation/episode) id", (fl) => sessionId(fl)),
  f("instance", "string", "Autonomous agent instance id", (fl) => instanceId(fl)),
  // L3/L4 transport
  f("l3l4.src_ip", "string", "Source IP", (fl) => layers(fl)?.l3l4?.src_ip ?? null),
  f("l3l4.dst_ip", "string", "Destination IP", (fl) => layers(fl)?.l3l4?.dst_ip ?? null),
  f("l3l4.src_port", "number", "Source port", (fl) => layers(fl)?.l3l4?.src_port ?? null),
  f("l3l4.dst_port", "number", "Destination port", (fl) => layers(fl)?.l3l4?.dst_port ?? null),
  f("l3l4.transport", "string", "Transport (tcp/udp)", (fl) => layers(fl)?.l3l4?.transport ?? null),
  f("l3l4.ip_version", "number", "IP version", (fl) => layers(fl)?.l3l4?.ip_version ?? null),
  // TLS / JA3
  f("tls.version", "string", "TLS version", (fl) => layers(fl)?.tls?.version ?? null),
  f("tls.cipher", "string", "Negotiated cipher", (fl) => layers(fl)?.tls?.cipher ?? null),
  f("tls.sni", "string", "SNI", (fl) => layers(fl)?.tls?.sni ?? null),
  f("tls.alpn", "string", "ALPN", (fl) => layers(fl)?.tls?.alpn ?? null),
  f("tls.ja3", "string", "Client JA3 (MD5)", (fl) => layers(fl)?.tls?.ja3 ?? null),
  f("tls.ja3_string", "string", "Client JA3 (raw)", (fl) => layers(fl)?.tls?.ja3_string ?? null),
  // HTTP (beyond bodies)
  f("http.version", "string", "HTTP version", (fl) => layers(fl)?.http?.version ?? null),
  f("http.reason", "string", "HTTP reason phrase", (fl) => layers(fl)?.http?.reason ?? null),
  // Timing
  f("timing.tcp_setup_ms", "number", "TCP connect (ms)", (fl) => layers(fl)?.timing?.tcp_setup_ms ?? null),
  f("timing.tls_setup_ms", "number", "TLS handshake (ms)", (fl) => layers(fl)?.timing?.tls_setup_ms ?? null),
  f("timing.ttfb_ms", "number", "Time to first byte (ms)", (fl) => layers(fl)?.timing?.ttfb_ms ?? null),
  f("timing.total_ms", "number", "Total (ms)", (fl) => layers(fl)?.timing?.total_ms ?? null),
  // L8 semantic (LLM dissector)
  f("l8.provider", "string", "LLM wire provider", (fl) => l8(fl)?.provider ?? null),
  f("l8.model", "string", "Requested model", (fl) => l8(fl)?.model ?? null),
  f("l8.tool", "string", "Tool the model INVOKED", (fl) => l8(fl)?.toolCalls ?? [], true),
  f("l8.tool_offered", "string", "Tool OFFERED to the model", (fl) => l8(fl)?.tools ?? [], true),
  f("l8.tokens.in", "number", "Prompt tokens", (fl) => l8(fl)?.usage?.input ?? null),
  f("l8.tokens.out", "number", "Completion tokens", (fl) => l8(fl)?.usage?.output ?? null),
  f("l8.stop", "string", "finish_reason / stop_reason", (fl) => l8(fl)?.stop ?? null),
  f("l8.response", "string", "Model answer text", (fl) => l8(fl)?.responseText ?? null),
];

/** path -> field, for O(1) resolution by the filter engine. */
export const WIRE_FIELDS: Record<string, WireField> = Object.fromEntries(
  WIRE_FIELD_LIST.map((field) => [field.path, field]),
);
