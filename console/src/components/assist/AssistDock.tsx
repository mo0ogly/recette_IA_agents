/**
 * Left-rail dock of the assist copilot ("Copilote IA").
 *
 * Collapsible column mounted once in App.tsx, left of the routed page:
 * backend selector (existing ai_backends, key never shown -- R8), two tabs
 * (Conversation = multi-turn chat, Journal = consolidated help insights),
 * message input with busy state, transport-error strip. Open state persists
 * in localStorage so the choice survives navigation and reloads.
 */

import { useEffect, useRef, useState } from "react";

import { listAiBackends } from "../../api/client";
import type { AiBackend } from "../../types/platform";

import { useAssist } from "./AssistProvider";
import ChatThread from "./ChatThread";
import InsightsJournal from "./InsightsJournal";
import "./assist.css";

const DOCK_OPEN_KEY = "assist.dock.open";

type DockTab = "chat" | "journal";

export default function AssistDock(): JSX.Element {
  const assist = useAssist();
  const [open, setOpen] = useState<boolean>(
    () => window.localStorage.getItem(DOCK_OPEN_KEY) !== "false",
  );
  const [tab, setTab] = useState<DockTab>("chat");
  const [backends, setBackends] = useState<AiBackend[]>([]);
  const [backendsError, setBackendsError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const insightsCountRef = useRef<number>(assist.insights.length);

  // A contextual-help answer (an IA button click) lands in the journal. When
  // the journal grows, surface it: open the dock if collapsed and switch to
  // the Journal tab, so the click has a visible result instead of a silent
  // badge on a tab the operator is not looking at. Guarded by a ref so the
  // initial rehydration (insights loaded from the session on mount) does not
  // force the tab on first render.
  useEffect(() => {
    if (assist.insights.length > insightsCountRef.current) {
      setTab("journal");
      setOpen((current) => {
        if (!current) {
          window.localStorage.setItem(DOCK_OPEN_KEY, "true");
        }
        return true;
      });
    }
    insightsCountRef.current = assist.insights.length;
  }, [assist.insights.length]);

  // A failed help/chat (no backend, unreachable provider) sets lastError; open
  // the dock so the error strip is not lost behind a collapsed rail.
  const lastErrorRef = useRef<string | null>(assist.lastError);
  useEffect(() => {
    if (assist.lastError !== null && assist.lastError !== lastErrorRef.current) {
      setOpen((current) => {
        if (!current) {
          window.localStorage.setItem(DOCK_OPEN_KEY, "true");
        }
        return true;
      });
    }
    lastErrorRef.current = assist.lastError;
  }, [assist.lastError]);

  useEffect(() => {
    let cancelled = false;
    listAiBackends()
      .then((list) => {
        if (cancelled) {
          return;
        }
        setBackends(list);
        setBackendsError(null);
        // Default to the first configured backend when none is chosen yet.
        if (assist.backendId === "" && list.length > 0) {
          assist.setBackendId(list[0].id);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setBackendsError(error instanceof Error ? error.message : String(error));
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot load
  }, []);

  function toggleOpen(): void {
    setOpen((current) => {
      window.localStorage.setItem(DOCK_OPEN_KEY, String(!current));
      return !current;
    });
  }

  async function submitDraft(): Promise<void> {
    const text = draft.trim();
    if (text.length === 0 || assist.chatBusy) {
      return;
    }
    setDraft("");
    await assist.sendChat(text);
    inputRef.current?.focus();
  }

  if (!open) {
    return (
      <aside className="assist-dock assist-dock-closed" data-testid="assist-dock" data-open="false">
        <button
          type="button"
          className="assist-collapse-btn"
          onClick={toggleOpen}
          aria-label="Ouvrir le Copilote IA"
          title="Ouvrir le Copilote IA"
        >
          IA
        </button>
        <span className="assist-dock-vertical-label">Copilote IA</span>
      </aside>
    );
  }

  return (
    <aside
      className="assist-dock"
      data-testid="assist-dock"
      data-open="true"
      data-assist-loc="assist-dock"
    >
      <header className="assist-dock-head">
        <span className="assist-dock-title">Copilote IA</span>
        <button
          type="button"
          className="assist-collapse-btn"
          onClick={toggleOpen}
          aria-label="Replier le Copilote IA"
          title="Replier le Copilote IA"
        >
          &lt;
        </button>
      </header>

      <div className="assist-backend-row">
        <label className="assist-backend-label" htmlFor="assist-backend-select">
          Backend IA
        </label>
        <select
          id="assist-backend-select"
          value={assist.backendId}
          onChange={(event) => assist.setBackendId(event.target.value)}
          disabled={backends.length === 0}
        >
          {backends.length === 0 ? <option value="">Aucun backend configure</option> : null}
          {backends.map((backend) => (
            <option key={backend.id} value={backend.id}>
              {backend.id}
              {backend.key_configured === false ? " (cle absente)" : ""}
            </option>
          ))}
        </select>
      </div>
      {backendsError !== null ? (
        <div className="assist-error" role="alert">
          Backends indisponibles: {backendsError}
        </div>
      ) : null}

      <div className="assist-level-row" role="group" aria-label="Niveau des explications">
        <span className="assist-backend-label">Niveau</span>
        <div className="assist-level-toggle">
          <button
            type="button"
            className="assist-level-btn"
            data-active={assist.level === "debutant"}
            onClick={() => assist.setLevel("debutant")}
          >
            Debutant
          </button>
          <button
            type="button"
            className="assist-level-btn"
            data-active={assist.level === "expert"}
            onClick={() => assist.setLevel("expert")}
          >
            Expert
          </button>
        </div>
      </div>

      <nav className="assist-tabs" aria-label="Sections du copilote">
        <button
          type="button"
          className="assist-tab"
          data-active={tab === "chat"}
          onClick={() => setTab("chat")}
        >
          Conversation
        </button>
        <button
          type="button"
          className="assist-tab"
          data-active={tab === "journal"}
          onClick={() => setTab("journal")}
        >
          Journal
          {assist.insights.length > 0 ? (
            <span className="assist-tab-count mono">{assist.insights.length}</span>
          ) : null}
        </button>
      </nav>

      <div className="assist-dock-body">
        {tab === "chat" ? (
          <ChatThread thread={assist.thread} busy={assist.chatBusy} />
        ) : (
          <InsightsJournal insights={assist.insights} />
        )}
      </div>

      {assist.lastError !== null ? (
        <div className="assist-error" role="alert" data-testid="assist-error">
          {assist.lastError}
        </div>
      ) : null}

      {tab === "chat" ? (
        <form
          className="assist-input-row"
          onSubmit={(event) => {
            event.preventDefault();
            void submitDraft();
          }}
        >
          <textarea
            ref={inputRef}
            className="assist-input"
            value={draft}
            placeholder="Votre question..."
            rows={2}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submitDraft();
              }
            }}
          />
          <button
            type="submit"
            className="assist-send-btn"
            disabled={assist.chatBusy || draft.trim().length === 0 || assist.backendId === ""}
          >
            {assist.chatBusy ? "..." : "Envoyer"}
          </button>
        </form>
      ) : (
        <div className="assist-journal-actions">
          <button type="button" onClick={() => void assist.clearSession()}>
            Effacer la session
          </button>
        </div>
      )}
    </aside>
  );
}
