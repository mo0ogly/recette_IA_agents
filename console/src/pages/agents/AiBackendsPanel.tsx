/**
 * AI-backends panel: list / create / delete / test the AI behind agents.
 *
 * Extracted from the Agents page to keep one responsibility per file. The
 * provider key can be stored per backend (write-only, R8) or resolved from
 * the environment at run time. The key is SENT only: the console never reads
 * a key back, it only renders a key_configured status. The "Test" button
 * calls the server-side connectivity probe and uses the stored key (or the
 * provider env var); key material never reaches the console on read. Each
 * probe outcome is also appended to the "Provider calls" LogConsole (the
 * audit stream has no provider/LLM event kind, so the panel logs its own).
 */

import { useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  createAiBackend,
  deleteAiBackend,
  deleteBackendSecret,
  setBackendSecret,
  testAiBackend,
} from "../../api/client";
import { LogConsole } from "../../components/LogConsole";
import type { LogLine } from "../../components/LogConsole";
import type { AiBackend, AiProvider } from "../../types/platform";

export interface AiBackendsPanelProps {
  backends: AiBackend[];
  onChanged: () => void | Promise<void>;
  onError: (message: string) => void;
}

/** Providers in factory order, each with the env var the server reads (R8). */
const PROVIDERS: Array<{ id: AiProvider; keyHint: string }> = [
  { id: "anthropic", keyHint: "ANTHROPIC_API_KEY" },
  { id: "openai", keyHint: "OPENAI_API_KEY" },
  { id: "gemini", keyHint: "GEMINI_API_KEY" },
  { id: "groq", keyHint: "GROQ_API_KEY" },
  { id: "mistral", keyHint: "MISTRAL_API_KEY" },
  { id: "deepseek", keyHint: "DEEPSEEK_API_KEY" },
  { id: "xai", keyHint: "XAI_API_KEY" },
  { id: "openai_compat", keyHint: "no key (or set on server)" },
];

const EMPTY: { id: string; provider: AiProvider; model: string; base_url: string } = {
  id: "",
  provider: "anthropic",
  model: "",
  base_url: "",
};

/** Per-backend probe outcome kept in component state, keyed by backend id. */
type TestState =
  | { phase: "testing" }
  | { phase: "ok"; latencyMs: number }
  | { phase: "error"; latencyMs: number; error: string };

function statusOf(state: TestState | undefined): "untested" | "ok" | "error" {
  if (state === undefined || state.phase === "testing") {
    return "untested";
  }
  return state.phase;
}

export default function AiBackendsPanel(props: AiBackendsPanelProps): JSX.Element {
  const { backends, onChanged, onError } = props;
  const [form, setForm] = useState(EMPTY);
  const [tests, setTests] = useState<Record<string, TestState>>({});
  // Per-backend draft key, keyed by backend id. Holds the in-flight value only:
  // it is cleared immediately after a successful save and never persisted or
  // logged (R8: the key is write-only from the console).
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  // Per-backend transient "saved" hint, shown briefly after a successful save.
  const [savedHints, setSavedHints] = useState<Record<string, boolean>>({});
  // Accumulated probe outcomes shown in the "Provider calls" LogConsole.
  const [calls, setCalls] = useState<LogLine[]>([]);
  const callSeqRef = useRef(0);

  function appendCall(level: LogLine["level"], id: string, text: string): void {
    callSeqRef.current += 1;
    const seq = callSeqRef.current;
    setCalls((prev) => [...prev, { seq, level, source: id, text }]);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const id = form.id.trim();
    if (id.length === 0) {
      onError("AI backend id is required.");
      return;
    }
    const backend: AiBackend = {
      id,
      provider: form.provider,
      model: form.model.trim(),
    };
    if (form.provider === "openai_compat") {
      backend.base_url = form.base_url.trim();
    }
    try {
      await createAiBackend(backend);
      setForm(EMPTY);
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDelete(id: string): Promise<void> {
    if (!window.confirm(`Delete AI backend "${id}"?`)) {
      return;
    }
    try {
      await deleteAiBackend(id);
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleSaveKey(id: string): Promise<void> {
    const apiKey = keyDrafts[id] ?? "";
    if (apiKey.length === 0) {
      // Empty input is blocked client-side (no 400 round-trip).
      return;
    }
    try {
      await setBackendSecret(id, apiKey);
      // Clear the draft immediately: the key never lingers in state (R8).
      setKeyDrafts((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      setSavedHints((prev) => ({ ...prev, [id]: true }));
      // Refresh so key_configured flips to true in the parent-owned list.
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleRemoveKey(id: string): Promise<void> {
    if (!window.confirm(`Remove the stored API key for "${id}"?`)) {
      return;
    }
    try {
      await deleteBackendSecret(id);
      setSavedHints((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleTest(id: string): Promise<void> {
    setTests((prev) => ({ ...prev, [id]: { phase: "testing" } }));
    try {
      const result = await testAiBackend(id);
      setTests((prev) => ({
        ...prev,
        [id]: result.ok
          ? { phase: "ok", latencyMs: result.latency_ms }
          : { phase: "error", latencyMs: result.latency_ms, error: result.error },
      }));
      if (result.ok) {
        appendCall("info", id, `backend ${id} ok in ${result.latency_ms} ms`);
      } else {
        appendCall(
          "error",
          id,
          `backend ${id} failed in ${result.latency_ms} ms: ${result.error}`,
        );
      }
    } catch (err) {
      // Transport / 404 failure: surface it in the row like a probe failure.
      const message = err instanceof Error ? err.message : String(err);
      setTests((prev) => ({
        ...prev,
        [id]: { phase: "error", latencyMs: 0, error: message },
      }));
      appendCall("error", id, `backend ${id} test failed: ${message}`);
    }
  }

  function renderKeyCell(backend: AiBackend): JSX.Element {
    const id = backend.id;
    const configured = backend.key_configured === true;
    const draft = keyDrafts[id] ?? "";
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
          onChange={(e) =>
            setKeyDrafts((prev) => ({ ...prev, [id]: e.target.value }))
          }
        />
        <button
          type="button"
          className="agents-btn"
          disabled={draft.length === 0}
          onClick={() => void handleSaveKey(id)}
        >
          Save key
        </button>
        {configured && (
          <button
            type="button"
            className="agents-btn agents-btn-danger"
            onClick={() => void handleRemoveKey(id)}
          >
            Remove key
          </button>
        )}
        {savedHints[id] && (
          <span className="agents-key-saved" data-testid="backend-key-saved">
            saved
          </span>
        )}
      </div>
    );
  }

  function renderTestCell(id: string): JSX.Element {
    const state = tests[id];
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

  return (
    <section className="agents-backends">
      <h2>AI backends (the AI behind agents)</h2>
      <p className="agents-backends-note">
        Provider + model only. The provider key is never stored here; it is
        resolved from the environment at run time (R8).
      </p>
      <table className="agents-table">
        <thead>
          <tr>
            <th>Id</th>
            <th>Provider</th>
            <th>Model</th>
            <th>Key</th>
            <th>Test</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {backends.length === 0 ? (
            <tr>
              <td colSpan={6} className="agents-empty">
                No AI backends configured.
              </td>
            </tr>
          ) : (
            backends.map((backend) => (
              <tr key={backend.id}>
                <td>{backend.id}</td>
                <td>{backend.provider}</td>
                <td>{backend.model}</td>
                <td className="agents-key-cell">{renderKeyCell(backend)}</td>
                <td>
                  <button
                    type="button"
                    className="agents-btn"
                    disabled={tests[backend.id]?.phase === "testing"}
                    onClick={() => void handleTest(backend.id)}
                  >
                    Test
                  </button>{" "}
                  {renderTestCell(backend.id)}
                  <span className="agents-key-hint">
                    Test uses the stored key (or the provider env var).
                  </span>
                </td>
                <td>
                  <button
                    type="button"
                    className="agents-btn agents-btn-danger"
                    onClick={() => void handleDelete(backend.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <div className="agents-run-log">
        <LogConsole
          title="Provider calls"
          lines={calls}
          onClear={() => setCalls([])}
        />
      </div>

      <form className="agents-form" onSubmit={(e) => void handleCreate(e)}>
        <h2>Create AI backend</h2>
        <div className="agents-form-row">
          <label htmlFor="backend-id">Id</label>
          <input
            id="backend-id"
            type="text"
            value={form.id}
            onChange={(e) => setForm((p) => ({ ...p, id: e.target.value }))}
            required
          />
        </div>
        <div className="agents-form-row">
          <label htmlFor="backend-provider">Provider</label>
          <select
            id="backend-provider"
            value={form.provider}
            onChange={(e) =>
              setForm((p) => ({ ...p, provider: e.target.value as AiProvider }))
            }
          >
            {PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id}
              </option>
            ))}
          </select>
          <span className="agents-key-hint">
            {PROVIDERS.find((p) => p.id === form.provider)?.keyHint}
          </span>
        </div>
        {form.provider === "openai_compat" && (
          <div className="agents-form-row">
            <label htmlFor="backend-base-url">Base URL</label>
            <input
              id="backend-base-url"
              type="text"
              placeholder="http://localhost:11434/v1"
              value={form.base_url}
              onChange={(e) => setForm((p) => ({ ...p, base_url: e.target.value }))}
              required
            />
          </div>
        )}
        <div className="agents-form-row">
          <label htmlFor="backend-model">Model</label>
          <input
            id="backend-model"
            type="text"
            placeholder="claude-opus-4-8, ..."
            value={form.model}
            onChange={(e) => setForm((p) => ({ ...p, model: e.target.value }))}
          />
        </div>
        <div className="agents-form-actions">
          <button type="submit" className="agents-btn agents-btn-primary">
            Create backend
          </button>
        </div>
      </form>
    </section>
  );
}
