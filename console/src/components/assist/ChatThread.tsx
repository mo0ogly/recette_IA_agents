/**
 * Chat thread of the Copilote IA dock: renders the bounded conversation
 * window with per-turn source styling (user / llm / error) and keeps the
 * scroll pinned to the newest exchange.
 */

import { useEffect, useRef } from "react";

import type { AssistMessage } from "../../types/assist";

export default function ChatThread({
  thread,
  busy,
}: {
  thread: AssistMessage[];
  busy: boolean;
}): JSX.Element {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // Guarded: jsdom (vitest) does not implement scrollIntoView.
    if (typeof endRef.current?.scrollIntoView === "function") {
      endRef.current.scrollIntoView({ block: "end" });
    }
  }, [thread.length, busy]);

  if (thread.length === 0 && !busy) {
    return (
      <div className="assist-empty" data-testid="assist-chat-empty">
        Posez une question sur la plateforme, un agent, une campagne ou un verdict.
      </div>
    );
  }

  return (
    <div className="assist-thread" data-testid="assist-chat-thread">
      {thread.map((message) => (
        <div
          key={message.id}
          className={`assist-msg assist-msg-${message.role}`}
          data-source={message.source}
        >
          <div className="assist-msg-body">{message.content}</div>
          {message.role === "assistant" && message.model !== null ? (
            <div className="assist-msg-meta mono">{message.model}</div>
          ) : null}
        </div>
      ))}
      {busy ? (
        <div className="assist-msg assist-msg-assistant assist-msg-pending" data-source="pending">
          <div className="assist-msg-body">
            <span className="assist-dots" aria-label="Reponse en cours" />
          </div>
        </div>
      ) : null}
      <div ref={endRef} />
    </div>
  );
}
