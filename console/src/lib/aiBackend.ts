/**
 * Shared AI-backend helpers used across the AI menus (Agents, Cockpit,
 * Dashboard). Centralizes the "is this a real-AI agent" rule and the backend
 * label format so the menus agree instead of each re-deriving them inline.
 */

import type { AgentConfig, AiBackend } from "../types/platform";

/** One-line label for a backend: "id (provider/model)". */
export function formatBackend(backend: AiBackend): string {
  return `${backend.id} (${backend.provider}/${backend.model})`;
}

/**
 * Real-AI axis: the agent runs a live provider only when its ai_mode is "real"
 * AND a backend is actually bound. ai_mode "real" with no ai_backend_id is a
 * misconfigured agent, not a real-AI one.
 */
export function isRealAi(agent: AgentConfig): boolean {
  return agent.ai_mode === "real" && Boolean(agent.ai_backend_id);
}

/** Real-target axis: the agent acts against a real server, not the lab. */
export function isRealTarget(agent: AgentConfig): boolean {
  return agent.runtime === "real";
}
