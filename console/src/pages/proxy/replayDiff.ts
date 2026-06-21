/**
 * replayDiff -- pure run-action summary for the replay-diff source.
 *
 * Distils an ordered run-event stream into a stable, line-per-action text so two
 * runs (an original and its replay) can be compared with the line-aligned
 * `lineDiff`. Each governed action an agent took surfaces as one `tool_call`
 * frame (`{type:"tool_call", data:{name, args}}`); the summary emits one line per
 * call as `"<name> <resource>"`, in stream order.
 *
 * Pure + deterministic (I4): no clock, no random, no DOM, no I/O -- a function of
 * its single input. Defensive against missing keys (a malformed frame degrades to
 * empty fields, never throws), which keeps the diff a faithful regression signal:
 * a divergence between two replays of the same recording is a real regression,
 * not a parsing artifact.
 */

import type { RunEvent } from "../../types/platform";

interface ToolCallData {
  name?: unknown;
  args?: { resource?: unknown } | null;
}

/** Best-effort string of an unknown value; non-strings (incl. undefined) -> "". */
function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * Stable one-line-per-action summary of a run (see module doc). Filters
 * `tool_call` frames and renders `"<name> <resource>"` trimmed, joined by "\n".
 */
export function runActionSummary(events: readonly RunEvent[]): string {
  return events
    .filter((e) => e.type === "tool_call")
    .map((e) => {
      const data = (e.data ?? {}) as ToolCallData;
      const name = asText(data.name);
      const resource = asText(data.args?.resource);
      return `${name} ${resource}`.trim();
    })
    .join("\n");
}
