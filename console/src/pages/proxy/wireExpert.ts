/**
 * wireExpert — expert-info signals over captured agent flows (DEFENSIVE audit).
 *
 * Wireshark's "Expert Information" equivalent, scoped to conformance auditing:
 * every signal is a deviation from what is EXPECTED/DECLARED or a hygiene issue
 * on an already-captured exchange — never attack detection or generation. Signals:
 *   - secret_in_clear : an API-key-shaped token sits UNMASKED in a body (the
 *     redaction contract says secrets must be masked at the source) -> warn.
 *   - ja3_drift       : one instance's TLS fingerprint (JA3) changes within a
 *     session (a same client should keep one JA3) -> note.
 *   - tls_downgrade   : an instance negotiates a lower TLS version than it did
 *     earlier in the capture -> note.
 *   - server_error    : status >= 500 (the target failed the exchange) -> warn.
 *
 * Pure and deterministic (I4): a function of the flows only, stable ordering, no
 * clock/network. Read-only: it inspects captured bytes, it never mutates a flow.
 */

import type { WireFlow } from "../../types/platform";
import { instanceId, readLayers, sessionId } from "./wireLayers";

export type ExpertSeverity = "note" | "warn" | "error";

export interface ExpertSignal {
  seq: number; // the flow the signal is anchored on
  severity: ExpertSeverity;
  kind: string;
  message: string;
}

// API-key shapes that must never travel unmasked (the "***" redaction marker is
// the masked form). Conservative patterns to avoid false positives on prose.
const _SECRET_PATTERNS: { label: string; re: RegExp }[] = [
  { label: "OpenAI", re: /\bsk-[A-Za-z0-9]{20,}\b/ },
  { label: "Anthropic", re: /\bsk-ant-[A-Za-z0-9-]{20,}\b/ },
  { label: "AWS", re: /\bAKIA[0-9A-Z]{16}\b/ },
  { label: "Bearer", re: /\bBearer\s+[A-Za-z0-9._-]{20,}\b/ },
  { label: "Google", re: /\bAIza[0-9A-Za-z_-]{35}\b/ },
];

function _secretIn(body: string): string | null {
  for (const { label, re } of _SECRET_PATTERNS) {
    if (re.test(body)) return label;
  }
  return null;
}

function _scanSecrets(flow: WireFlow, out: ExpertSignal[]): void {
  const hit = _secretIn(flow.request_body) ?? _secretIn(flow.response_body);
  if (hit !== null) {
    out.push({
      seq: flow.seq,
      severity: "warn",
      kind: "secret_in_clear",
      message: `${hit}-shaped secret present unmasked in a body (should be redacted at source)`,
    });
  }
}

/** JA3 drift + TLS downgrade are per-instance temporal checks, so they need the
 *  whole ordered capture, not a single flow. */
function _scanTlsPerInstance(flows: WireFlow[], out: ExpertSignal[]): void {
  const lastJa3 = new Map<string, string>();
  const lastVer = new Map<string, string>();
  for (const flow of flows) {
    const inst = instanceId(flow);
    if (inst === null) continue;
    const tls = readLayers(flow)?.tls;
    if (!tls) continue;
    if (tls.ja3) {
      const prev = lastJa3.get(inst);
      if (prev !== undefined && prev !== tls.ja3) {
        out.push({
          seq: flow.seq,
          severity: "note",
          kind: "ja3_drift",
          message: `instance ${inst} JA3 changed within the capture (${prev.slice(0, 8)} -> ${tls.ja3.slice(0, 8)})`,
        });
      }
      lastJa3.set(inst, tls.ja3);
    }
    if (tls.version) {
      const prev = lastVer.get(inst);
      if (prev !== undefined && _tlsRank(tls.version) < _tlsRank(prev)) {
        out.push({
          seq: flow.seq,
          severity: "note",
          kind: "tls_downgrade",
          message: `instance ${inst} negotiated ${tls.version} after ${prev} earlier`,
        });
      }
      lastVer.set(inst, tls.version);
    }
  }
}

/** Order TLS versions so a downgrade is a strictly lower rank. Unknown -> 0. */
function _tlsRank(version: string): number {
  const v = version.toLowerCase();
  if (v.includes("1.3")) return 3;
  if (v.includes("1.2")) return 2;
  if (v.includes("1.1")) return 1;
  if (v.includes("1.0")) return 1;
  return 0;
}

function _scanServerError(flow: WireFlow, out: ExpertSignal[]): void {
  if (flow.status_code >= 500) {
    out.push({
      seq: flow.seq,
      severity: "warn",
      kind: "server_error",
      message: `target returned ${flow.status_code}${sessionId(flow) ? ` (session ${sessionId(flow)})` : ""}`,
    });
  }
}

const _SEV_ORDER: Record<ExpertSeverity, number> = { error: 0, warn: 1, note: 2 };

/** Compute all expert-info signals over the flows, most-severe first then by seq. */
export function computeExpertInfo(flows: WireFlow[]): ExpertSignal[] {
  const out: ExpertSignal[] = [];
  for (const flow of flows) {
    _scanSecrets(flow, out);
    _scanServerError(flow, out);
  }
  _scanTlsPerInstance(flows, out);
  return out.sort((a, b) => _SEV_ORDER[a.severity] - _SEV_ORDER[b.severity] || a.seq - b.seq);
}

/** Count by severity, for the panel header badge. */
export function expertSummary(signals: ExpertSignal[]): Record<ExpertSeverity, number> {
  const acc: Record<ExpertSeverity, number> = { note: 0, warn: 0, error: 0 };
  for (const s of signals) acc[s.severity] += 1;
  return acc;
}
