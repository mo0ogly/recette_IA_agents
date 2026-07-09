/**
 * wireRunTimeline -- reconstruct a run's decision timeline from its wire flows.
 *
 * The wire panel captures agent <-> target bytes; grouped by run and ordered by
 * capture sequence, those bytes ARE the run's story: each LLM call is a
 * reasoning step (what the model answered + which tool it decided to call), each
 * non-LLM call is the effect that reasoning produced on the wire (the actual
 * side effect). Laid end to end in order, they let an operator scan a run and
 * pinpoint the exact step where an undesired action first appears -- the
 * "DECIDE" <-> "DO" correlation the platform's legibility principle calls for.
 *
 * Pure and deterministic (I4): a function of the flow bytes only. Display-only,
 * never a judge/decision/replay input.
 */

import type { WireFlow } from "../../types/platform";
import { decodeLlmFlow } from "./wireLlmDecode";

/** A reasoning step: an LLM call decoded into what the model answered and the
 *  tools it chose to invoke at this turn. `toolCalls` non-empty = the model
 *  DECIDED an action here (the candidate "moment" of an undesired action). */
export interface DecisionStep {
  seq: number;
  kind: "decision";
  model: string | null;
  /** The model's textual answer / reasoning at this turn (null if unparseable). */
  answer: string | null;
  /** Tools/functions the model decided to invoke at this turn. */
  toolCalls: string[];
}

/** An effect step: a non-LLM wire call -- the actual side effect executed
 *  (e.g. the HTTP call the decided tool performed). A mutating method
 *  (POST/PUT/PATCH/DELETE) marks a state-changing action on the target. */
export interface EffectStep {
  seq: number;
  kind: "effect";
  method: string;
  host: string;
  path: string;
  status: number;
  ok: boolean;
  /** True when the method changes target state (the class of action worth
   *  scrutinising for "undesired action" -- a GET rarely is). */
  mutating: boolean;
}

export type RunStep = DecisionStep | EffectStep;

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * Build the ordered decision timeline of a run from its (already run-scoped)
 * wire flows. Flows are sorted by capture sequence so the timeline reads in the
 * order things happened; each flow becomes a decision step (LLM call) or an
 * effect step (any other call). The input is not mutated.
 */
export function buildRunTimeline(flows: WireFlow[]): RunStep[] {
  return [...flows]
    .sort((a, b) => a.seq - b.seq)
    .map((f): RunStep => {
      const llm = decodeLlmFlow(f);
      if (llm !== null) {
        return {
          seq: f.seq,
          kind: "decision",
          model: llm.model,
          answer: llm.responseText,
          toolCalls: llm.toolCalls,
        };
      }
      return {
        seq: f.seq,
        kind: "effect",
        method: f.method,
        host: f.host,
        path: f.path,
        status: f.status_code,
        ok: f.ok,
        mutating: MUTATING_METHODS.has(f.method.toUpperCase()),
      };
    });
}

/** Whether a step is an "action" worth flagging in the timeline: a decision that
 *  invoked a tool, or a mutating effect. Pure helper for the view's highlight. */
export function isActionStep(step: RunStep): boolean {
  if (step.kind === "decision") return step.toolCalls.length > 0;
  return step.mutating;
}
