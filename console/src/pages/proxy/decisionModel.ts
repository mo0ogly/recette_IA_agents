/**
 * decisionModel -- pure helpers distilling a run's events into the DECIDE
 * altitude (the agent's "why" behind each action), correlated to the session's
 * exchanges by order. Pure (I4), no DOM. The i-th tool_call frame maps to the
 * i-th governed exchange.
 *
 * Frame shapes are defensive: the API wraps a runner payload as
 * `{seq, type, data}` (so a real tool_call is `{type:"tool_call", data:{name,
 * args, ...}}`), while a flat frame may carry `tool_name`/`text` at the top
 * level. We read whichever is present and never throw on a missing key.
 */
import type { RunEvent } from "../../types/platform";

export interface Decision {
  index: number;
  toolName?: string;
  summary: string;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

export function decisionsFromEvents(events: RunEvent[]): Decision[] {
  const out: Decision[] = [];
  let lastStepText = "";
  let i = 0;
  for (const e of events) {
    const top = e as Record<string, unknown>;
    const data = rec(top.data);
    if (e.type === "step") {
      // carry the most recent reasoning text to attach to the next tool_call.
      // lane_b nests it under data.decision.text; a flat step uses data.text or
      // a top-level text.
      const decision = rec(data.decision);
      lastStepText =
        str(top.text) || str(data.text) || str(decision.text) || lastStepText;
    } else if (e.type === "tool_call") {
      // real wire: data.name ; flat fixture: top-level tool_name (or data.tool_name).
      const toolName =
        str(top.tool_name) || str(data.name) || str(data.tool_name) || undefined;
      const summary =
        [toolName, lastStepText].filter(Boolean).join(" -- ") ||
        (toolName ?? "tool_call");
      out.push({ index: i, toolName, summary });
      i += 1;
      lastStepText = "";
    }
  }
  return out;
}

export function decisionForIndex(decisions: Decision[], i: number): Decision | undefined {
  return decisions[i];
}
