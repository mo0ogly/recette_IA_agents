/**
 * benchModel — client + types for the probe-vs-wire precision/recall bench.
 *
 * The bench (POST /probe/bench) scores the eBPF discovery probe against the wire
 * truth: it joins the probe's `connect:ip:port` detections to the buffered wire
 * flows by real IP:port (the wire L3/L4 layer is ground truth) and returns
 * TP/FN/FP + precision/recall/F1. Types live here (not in the size-capped
 * api/client.ts) and the call reuses its exported `request` helper.
 *
 * `recall` is the headline: did the scanner miss a real egress (FN)? `precision`
 * is softer — the wire only sees proxied HTTP(S), so a probe-only endpoint (FP,
 * e.g. a DNS resolver) is not necessarily a probe error.
 */

import { request } from "../../api/client";

/** One IP:port endpoint and how the two observers saw it. */
export interface BenchEndpoint {
  endpoint: string;
  ip: string;
  port: number | null;
  in_wire: boolean;
  in_probe: boolean;
  verdict: "tp" | "fn" | "fp";
  host: string | null;
  ja3: string | null;
}

/** Detector scorecard: counts, rates (null when undefined), per-endpoint rows. */
export interface BenchReport {
  tp: number;
  fp: number;
  fn: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  wire_endpoints: number;
  probe_endpoints: number;
  /** Wire flows with no L3/L4 IP (legacy overlay): partial-coverage honesty. */
  wire_flows_without_ip: number;
  endpoints: BenchEndpoint[];
}

/** POST /probe/bench response envelope. */
export interface ProbeBenchResult {
  recording_status: string | null;
  wire_flows_total: number;
  report: BenchReport;
}

/** Run one bench: a bounded probe capture joined to the current wire buffer. */
export function runProbeBench(agents: string[], durationMs?: number): Promise<ProbeBenchResult> {
  return request<ProbeBenchResult>("/probe/bench", {
    method: "POST",
    body: JSON.stringify({ agents, duration_ms: durationMs }),
  });
}

/** Format a rate as a percentage, or "n/a" when undefined (empty denominator). */
export function pct(rate: number | null): string {
  return rate === null ? "n/a" : `${Math.round(rate * 100)}%`;
}

/** Human label + css modifier for a verdict. */
export function verdictLabel(verdict: BenchEndpoint["verdict"]): { text: string; cls: string } {
  if (verdict === "tp") return { text: "detecte", cls: "tp" };
  if (verdict === "fn") return { text: "manque (ghost)", cls: "fn" };
  return { text: "probe seul", cls: "fp" };
}
