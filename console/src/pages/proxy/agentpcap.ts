/**
 * agentpcap — portable capture format for agent wire flows (the "pcap" of the
 * agent-IA analyzer).
 *
 * A versioned, self-contained JSON envelope carrying a selection of captured
 * flows plus a SEQUENCE-INTEGRITY chain: each link hashes the previous link and
 * the canonical serialization of one flow, so reordering, dropping or editing a
 * flow breaks verification on import (I1 spirit: the capture is append-only
 * evidence). The chain is a deterministic FNV-1a digest — a tamper-evidence
 * seal for auditors, NOT cryptographic authentication (no key, no signature).
 *
 * Pure and deterministic (I4): same flows -> byte-identical file; no clock, no
 * randomness. Import verifies then returns the flows for OFFLINE inspection in
 * the panel (no backend needed) — the shareable-capture workflow of Wireshark.
 */

import type { WireFlow } from "../../types/platform";

export const AGENTPCAP_FORMAT = "agentpcap";
export const AGENTPCAP_VERSION = 1;

export interface AgentPcapFile {
  format: typeof AGENTPCAP_FORMAT;
  version: number;
  flow_count: number;
  flows: WireFlow[];
  /** Per-flow chained digests; chain[i] seals flows[0..i]. */
  chain: string[];
}

export interface AgentPcapImport {
  flows: WireFlow[];
  /** True when the integrity chain recomputes identically. */
  verified: boolean;
  error: string | null;
}

/** FNV-1a 32-bit over a string, hex-encoded. Deterministic, dependency-free. */
function _fnv1a(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    // 32-bit FNV prime multiply, kept in uint32 space.
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

/** Canonical serialization of a flow for hashing: keys sorted, no spacing. */
function _canonical(flow: WireFlow): string {
  const rec = flow as unknown as Record<string, unknown>;
  const keys = Object.keys(rec).sort();
  return JSON.stringify(rec, keys);
}

/** Chain the flows in capture order: link i = fnv(link[i-1] + canonical(flow)). */
export function chainDigests(flows: WireFlow[]): string[] {
  const out: string[] = [];
  let prev = "genesis";
  for (const flow of flows) {
    prev = _fnv1a(`${prev}\n${_canonical(flow)}`);
    out.push(prev);
  }
  return out;
}

/** Serialize flows to the portable .agentpcap JSON (pretty, diff-friendly). */
export function toAgentPcap(flows: WireFlow[]): string {
  const file: AgentPcapFile = {
    format: AGENTPCAP_FORMAT,
    version: AGENTPCAP_VERSION,
    flow_count: flows.length,
    flows,
    chain: chainDigests(flows),
  };
  return JSON.stringify(file, null, 2);
}

/** Parse + verify a .agentpcap file. Malformed input never throws: it returns
 *  an explicit error (the panel surfaces it, the view stays usable). */
export function fromAgentPcap(text: string): AgentPcapImport {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { flows: [], verified: false, error: "fichier illisible (JSON invalide)" };
  }
  const file = parsed as Partial<AgentPcapFile>;
  if (file.format !== AGENTPCAP_FORMAT) {
    return { flows: [], verified: false, error: "format inattendu (pas un .agentpcap)" };
  }
  if (file.version !== AGENTPCAP_VERSION) {
    return {
      flows: [],
      verified: false,
      error: `version ${String(file.version)} non supportee (attendu ${AGENTPCAP_VERSION})`,
    };
  }
  if (!Array.isArray(file.flows) || !Array.isArray(file.chain)) {
    return { flows: [], verified: false, error: "enveloppe incomplete (flows/chain manquants)" };
  }
  const flows = file.flows as WireFlow[];
  const expected = chainDigests(flows);
  const verified =
    expected.length === file.chain.length && expected.every((d, i) => d === file.chain?.[i]);
  return {
    flows,
    verified,
    error: verified ? null : "chaine d'integrite invalide (capture alteree ou reordonnee)",
  };
}
