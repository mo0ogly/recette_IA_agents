/**
 * Types for the assist copilot ("Copilote IA"): the left dock chat, the
 * contextual-help journal, and the prompt catalog. Mirrors the /assist API
 * contract (raw JSON, no envelope). Source of truth:
 * docs/tracking/cockpit-llm/API-CONTRACT.md + recette/api/routers/assist.py.
 */

/** Discriminant of every LLM-backed assist response (fail-safe: never a 500). */
export type AssistSource = "llm" | "error";

/** One entry of a session's chat thread. */
export interface AssistMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** "user" for operator turns; "llm" or "error" for assistant turns. */
  source: "user" | "llm" | "error";
  model: string | null;
  created_at: string;
}

/** POST /assist/chat response. */
export interface AssistChatResponse {
  reply: string;
  source: AssistSource;
  model: string | null;
  error: string | null;
  thread: AssistMessage[];
}

/** One consolidated contextual-help entry of the session journal. */
export interface AssistInsight {
  id: string;
  topic: string;
  label: string;
  answer: string;
  model: string | null;
  created_at: string;
}

/** GET /assist/sessions/{id} response (unknown session = empty memory). */
export interface AssistSessionMemory {
  thread: AssistMessage[];
  insights: AssistInsight[];
}

/** POST /assist/help response. insight is null on source "error" (nothing
 *  is journaled for a failed call); otherwise it is the journaled entry. */
export interface AssistHelpResponse {
  answer: string;
  source: AssistSource;
  model: string | null;
  error: string | null;
  insight: AssistInsight | null;
}

/** Where a prompt is used in the UI ("Localiser dans l'UI" support). */
export interface AssistPromptLocalisation {
  view: string;
  trigger: string;
  endpoint: string;
  component: string;
  loc: string;
}

/** One prompt catalog entry (default in code, override persisted server-side). */
export interface AssistPromptEntry {
  id: string;
  kind: "text" | "json";
  label: string;
  description: string;
  localisation: AssistPromptLocalisation;
  default: unknown;
  value: unknown;
  overridden: boolean;
}

/** GET /assist/prompts response. */
export interface AssistPromptsResponse {
  prompts: AssistPromptEntry[];
}

/** One grounding topic exposed by GET /assist/topics. */
export interface AssistTopicInfo {
  topic: string;
  label: string;
  params: string[];
}

/** GET /assist/topics response. */
export interface AssistTopicsResponse {
  topics: AssistTopicInfo[];
}
