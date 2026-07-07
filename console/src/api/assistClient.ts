/**
 * Typed client for the /assist endpoints (Copilote IA).
 *
 * Kept out of client.ts on purpose (that file is already over the LOC
 * ceiling); shares its request<T> helper so base URL, headers and ApiError
 * semantics stay identical. Raw JSON responses, no envelope.
 */

import type {
  AssistChatResponse,
  AssistHelpResponse,
  AssistPromptEntry,
  AssistPromptsResponse,
  AssistSessionMemory,
  AssistTopicsResponse,
} from "../types/assist";

import { request } from "./client";

export function listAssistPrompts(): Promise<AssistPromptsResponse> {
  return request<AssistPromptsResponse>("/assist/prompts", { method: "GET" });
}

export function setAssistPrompt(id: string, value: unknown): Promise<AssistPromptEntry> {
  return request<AssistPromptEntry>(`/assist/prompts/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export function resetAssistPrompt(id: string): Promise<void> {
  return request<void>(`/assist/prompts/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function postAssistChat(body: {
  session_id: string;
  backend_id: string;
  message: string;
}): Promise<AssistChatResponse> {
  return request<AssistChatResponse>("/assist/chat", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function postAssistHelp(body: {
  session_id: string;
  backend_id: string;
  topic: string;
  label: string;
  params?: Record<string, string>;
  level?: string;
}): Promise<AssistHelpResponse> {
  return request<AssistHelpResponse>("/assist/help", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getAssistSession(sessionId: string): Promise<AssistSessionMemory> {
  return request<AssistSessionMemory>(`/assist/sessions/${encodeURIComponent(sessionId)}`, {
    method: "GET",
  });
}

export function clearAssistSession(sessionId: string): Promise<void> {
  return request<void>(`/assist/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function listAssistTopics(): Promise<AssistTopicsResponse> {
  return request<AssistTopicsResponse>("/assist/topics", { method: "GET" });
}
