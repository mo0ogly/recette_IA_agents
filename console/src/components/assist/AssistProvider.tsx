/**
 * Context provider for the assist copilot ("Copilote IA").
 *
 * Owns the whole client-side assist state so ANY page can drop an
 * AssistButton (one line) and the answer lands in the shared left dock:
 * - session identity (localStorage UUID) and chosen ai_backend (localStorage);
 * - the consolidated memories (chat thread + insights journal), rehydrated
 *   from the server on mount (the server is the source of truth);
 * - the sendChat / askHelp / clearSession actions with busy + error state.
 *
 * Fail-safe mirror of the backend contract: a response with source "error"
 * is rendered in place, an ApiError becomes a banner, never a crash.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  clearAssistSession,
  getAssistSession,
  postAssistChat,
  postAssistHelp,
} from "../../api/assistClient";
import type { AssistInsight, AssistMessage } from "../../types/assist";

const SESSION_KEY = "assist.session.id";
const BACKEND_KEY = "assist.backend.id";

function mintSessionId(): string {
  const uuid =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `s-${uuid}`;
}

function loadSessionId(): string {
  const existing = window.localStorage.getItem(SESSION_KEY);
  if (existing) {
    return existing;
  }
  const minted = mintSessionId();
  window.localStorage.setItem(SESSION_KEY, minted);
  return minted;
}

export interface AssistContextValue {
  sessionId: string;
  backendId: string;
  setBackendId: (id: string) => void;
  thread: AssistMessage[];
  insights: AssistInsight[];
  chatBusy: boolean;
  /** Topics with an in-flight help request (drives per-button spinners). */
  busyTopics: ReadonlySet<string>;
  /** Last transport-level failure (ApiError/network), null when healthy. */
  lastError: string | null;
  sendChat: (message: string) => Promise<void>;
  askHelp: (topic: string, label: string, params?: Record<string, string>) => Promise<void>;
  clearSession: () => Promise<void>;
}

const AssistContext = createContext<AssistContextValue | null>(null);

export function useAssist(): AssistContextValue {
  const value = useContext(AssistContext);
  if (value === null) {
    throw new Error("useAssist must be used inside <AssistProvider>");
  }
  return value;
}

/** Nullable variant for optional consumers (AssistButton renders nothing
 *  outside the provider, so pages stay testable standalone). */
export function useAssistOptional(): AssistContextValue | null {
  return useContext(AssistContext);
}

export default function AssistProvider({ children }: { children: ReactNode }): JSX.Element {
  const [sessionId] = useState<string>(loadSessionId);
  const [backendId, setBackendIdState] = useState<string>(
    () => window.localStorage.getItem(BACKEND_KEY) ?? "",
  );
  const [thread, setThread] = useState<AssistMessage[]>([]);
  const [insights, setInsights] = useState<AssistInsight[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [busyTopics, setBusyTopics] = useState<ReadonlySet<string>>(new Set());
  const [lastError, setLastError] = useState<string | null>(null);

  // Rehydrate the consolidated memory once: an API restart or a page reload
  // must not silently show an empty dock when the server still has the thread.
  useEffect(() => {
    let cancelled = false;
    getAssistSession(sessionId)
      .then((memory) => {
        if (cancelled) {
          return;
        }
        setThread(memory.thread);
        setInsights(memory.insights);
      })
      .catch(() => {
        // API unreachable at mount: the dock renders empty; the first action
        // will surface the transport error.
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const setBackendId = useCallback((id: string) => {
    setBackendIdState(id);
    window.localStorage.setItem(BACKEND_KEY, id);
  }, []);

  const sendChat = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (text.length === 0 || backendId.length === 0) {
        return;
      }
      setChatBusy(true);
      setLastError(null);
      try {
        const response = await postAssistChat({
          session_id: sessionId,
          backend_id: backendId,
          message: text,
        });
        // The server returns the authoritative thread (both turns appended,
        // bounded window) -- replace, never merge.
        setThread(response.thread);
      } catch (error) {
        setLastError(error instanceof Error ? error.message : String(error));
      } finally {
        setChatBusy(false);
      }
    },
    [backendId, sessionId],
  );

  const askHelp = useCallback(
    async (topic: string, label: string, params?: Record<string, string>) => {
      if (backendId.length === 0) {
        setLastError("Selectionnez un backend IA dans le dock Copilote IA.");
        return;
      }
      setBusyTopics((current) => new Set(current).add(topic));
      setLastError(null);
      try {
        const response = await postAssistHelp({
          session_id: sessionId,
          backend_id: backendId,
          topic,
          label,
          params,
        });
        if (response.insight !== null) {
          setInsights((current) => [...current, response.insight!]);
        } else if (response.source === "error" && response.error !== null) {
          setLastError(response.error);
        }
      } catch (error) {
        setLastError(error instanceof Error ? error.message : String(error));
      } finally {
        setBusyTopics((current) => {
          const next = new Set(current);
          next.delete(topic);
          return next;
        });
      }
    },
    [backendId, sessionId],
  );

  const clearSession = useCallback(async () => {
    setLastError(null);
    try {
      await clearAssistSession(sessionId);
      setThread([]);
      setInsights([]);
    } catch (error) {
      setLastError(error instanceof Error ? error.message : String(error));
    }
  }, [sessionId]);

  const value = useMemo<AssistContextValue>(
    () => ({
      sessionId,
      backendId,
      setBackendId,
      thread,
      insights,
      chatBusy,
      busyTopics,
      lastError,
      sendChat,
      askHelp,
      clearSession,
    }),
    [
      sessionId,
      backendId,
      setBackendId,
      thread,
      insights,
      chatBusy,
      busyTopics,
      lastError,
      sendChat,
      askHelp,
      clearSession,
    ],
  );

  return <AssistContext.Provider value={value}>{children}</AssistContext.Provider>;
}
