/**
 * Pure mapping of streamed Lane B run frames to displayable log lines for the
 * Agents page run log. No React, no side effects.
 */

import type { LogLine } from "../../components/LogConsole";
import type { RunFrame } from "../../hooks/useRunStream";
import type { AgentConfig } from "../../types/platform";

/** Compact one-line summary of a streamed lane_b frame. */
export function frameText(frame: RunFrame): string {
  const d = frame.data;
  switch (frame.type) {
    case "start":
      return `start (kind=${String(d.kind ?? "")})`;
    case "step": {
      const action = d.action as Record<string, unknown> | undefined;
      const at = action
        ? `${String(action.action_type)}@${String(action.target_system)}`
        : "(no action)";
      return `step #${String(d.index ?? "")}: ${at}`;
    }
    case "tool_call": {
      const args = (d.args as Record<string, unknown> | undefined) ?? {};
      const keys = Object.keys(args);
      const summary = keys.length
        ? ` (${keys.map((k) => `${k}=${String(args[k])}`).join(", ")})`
        : "";
      return `tool_call #${String(d.index ?? "")}: ${String(d.name ?? "")}${summary}`;
    }
    case "result": {
      const actions = (d.actions as unknown[] | undefined) ?? [];
      return `result: ${actions.length} action(s) recorded`;
    }
    case "error":
      return `error: ${String(d.message ?? "")}`;
    case "end":
      return `end (status=${String(d.status ?? "")})`;
    default:
      return frame.type;
  }
}

/** Map one streamed run frame to a displayable log line. */
export function frameToLogLine(frame: RunFrame, source: string): LogLine {
  const failed = frame.type === "error" || frame.data.error !== undefined;
  return {
    seq: frame.seq,
    level: failed ? "error" : "info",
    source,
    text: frameText(frame),
  };
}

/** Mock brain when declared, or (legacy records) when no backend is bound. */
export function isMockAgent(agent: AgentConfig): boolean {
  return agent.ai_mode === "mock" || (agent.ai_mode === undefined && !agent.ai_backend_id);
}
