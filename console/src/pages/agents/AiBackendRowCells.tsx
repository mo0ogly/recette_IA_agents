/**
 * Presentational cells for one AI-backend row (key management, ask, test).
 *
 * Extracted from AiBackendsPanel so the panel stays under the .tsx LOC
 * ceiling. These are pure: all state lives in the parent and is passed in
 * via props, so the DOM (classes, data-testid, roles, copy) is byte-for-byte
 * what the panel rendered inline. No logic moves here, only markup.
 */

import type { AiBackend } from "../../types/platform";

/** Per-backend connectivity-probe outcome (the "Test" button). */
export type TestState =
  | { phase: "testing" }
  | { phase: "ok"; latencyMs: number }
  | { phase: "error"; latencyMs: number; error: string };

/** Per-backend free-text prompt outcome (the "Ask the AI" affordance). */
export type AskState =
  | { phase: "asking" }
  | { phase: "ok"; latencyMs: number; text: string }
  | { phase: "error"; latencyMs: number; error: string };

/** Status the row dot reflects: untested (grey), ok (green), error (red). */
export function statusOf(state: TestState | undefined): "untested" | "ok" | "error" {
  if (state === undefined || state.phase === "testing") {
    return "untested";
  }
  return state.phase;
}

export interface KeyCellProps {
  backend: AiBackend;
  draft: string;
  onDraftChange: (value: string) => void;
  onSave: () => void;
  onRemove: () => void;
  saved: boolean;
}

/** Key chip + write-only key input + save/remove (R8: never reads a key back). */
export function KeyCell(props: KeyCellProps): JSX.Element {
  const { backend, draft, onDraftChange, onSave, onRemove, saved } = props;
  const id = backend.id;
  const configured = backend.key_configured === true;
  const inputId = `backend-key-${id}`;
  return (
    <div className="agents-key-manage">
      <span
        className="agents-key-chip"
        data-testid="backend-key-status"
        data-key-configured={configured ? "true" : "false"}
      >
        {configured ? "key set" : "no key"}
      </span>
      <label className="agents-visually-hidden" htmlFor={inputId}>
        {`API key for ${id}`}
      </label>
      <input
        id={inputId}
        type="password"
        autoComplete="off"
        className="agents-key-input"
        placeholder="paste API key"
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
      />
      <button
        type="button"
        className="agents-btn"
        disabled={draft.length === 0}
        onClick={onSave}
      >
        Save key
      </button>
      {configured && (
        <button
          type="button"
          className="agents-btn agents-btn-danger"
          onClick={onRemove}
        >
          Remove key
        </button>
      )}
      {saved && (
        <span className="agents-key-saved" data-testid="backend-key-saved">
          saved
        </span>
      )}
    </div>
  );
}

export interface AskCellProps {
  id: string;
  state: AskState | undefined;
  draft: string;
  onDraftChange: (value: string) => void;
  onAsk: () => void;
}

/** Free-text prompt to the model behind the backend, with answer/error panel. */
export function AskCell(props: AskCellProps): JSX.Element {
  const { id, state, draft, onDraftChange, onAsk } = props;
  const asking = state?.phase === "asking";
  const inputId = `backend-ask-${id}`;
  return (
    <div className="agents-ask" data-testid="backend-ask">
      <span className="agents-ask-caption" aria-hidden="true">
        Ask the model
      </span>
      <label className="agents-visually-hidden" htmlFor={inputId}>
        {`Ask the model behind ${id}`}
      </label>
      <input
        id={inputId}
        type="text"
        className="agents-ask-input"
        placeholder="Ask the model something..."
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
      />
      <button
        type="button"
        className="agents-btn"
        disabled={draft.trim().length === 0 || asking}
        onClick={onAsk}
      >
        Ask
      </button>
      {asking && <span className="agents-ask-spinner">asking...</span>}
      {state?.phase === "ok" && (
        <div
          className="agents-ask-answer"
          data-testid="backend-ask-answer"
          data-status="ok"
        >
          <pre className="agents-ask-text">{state.text}</pre>
          <span className="agents-ask-latency">{state.latencyMs} ms</span>
        </div>
      )}
      {state?.phase === "error" && (
        <div
          className="agents-ask-answer agents-ask-error"
          data-testid="backend-ask-answer"
          data-status="error"
        >
          <span>{state.error}</span>
          <span className="agents-ask-latency">{state.latencyMs} ms</span>
        </div>
      )}
    </div>
  );
}

export interface TestCellProps {
  state: TestState | undefined;
}

/** Status dot + latency / error text for the connectivity probe. */
export function TestCell(props: TestCellProps): JSX.Element {
  const { state } = props;
  return (
    <span className="agents-test-result">
      <span
        className="agents-status-dot"
        data-testid="backend-test-status"
        data-status={statusOf(state)}
      />
      {state?.phase === "testing" && <span>testing...</span>}
      {state?.phase === "ok" && <span>{state.latencyMs} ms</span>}
      {state?.phase === "error" && (
        <span className="agents-test-error" title={state.error}>
          {state.error}
        </span>
      )}
    </span>
  );
}
