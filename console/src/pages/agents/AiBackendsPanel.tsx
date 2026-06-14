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

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  createAiBackend,
  deleteAiBackend,
  deleteBackendSecret,
  listAiProviders,
  setBackendSecret,
  testAiBackend,
} from "../../api/client";
import { LogConsole } from "../../components/LogConsole";
import type { LogLine } from "../../components/LogConsole";
import { AskCell, KeyCell, TestCell } from "./AiBackendRowCells";
import type { AskState, TestState } from "./AiBackendRowCells";
import type { AiBackend, AiProvider, AiProviderInfo } from "../../types/platform";

export interface AiBackendsPanelProps {
  backends: AiBackend[];
  onChanged: () => void | Promise<void>;
  onError: (message: string) => void;
}

/** Human hint for the write-only key field: the env var name, or a note when no
 * key is needed. Derived from the catalog so a new provider needs no edit here. */
function keyHintFor(info: AiProviderInfo | undefined): string {
  if (info === undefined) return "";
  if (info.env_key !== null) return info.env_key;
  return "no key (or set on server)";
}

const EMPTY: { id: string; provider: string; model: string; base_url: string } = {
  id: "",
  provider: "anthropic",
  model: "",
  base_url: "",
};

export default function AiBackendsPanel(props: AiBackendsPanelProps): JSX.Element {
  const { backends, onChanged, onError } = props;
  const [form, setForm] = useState(EMPTY);
  // Provider catalog fetched from the backend (single source of truth). The
  // dropdown is built from this, so adding a provider server-side surfaces here
  // with no frontend change.
  const [providers, setProviders] = useState<AiProviderInfo[]>([]);

  useEffect(() => {
    let alive = true;
    listAiProviders()
      .then((list) => {
        if (alive) setProviders(list);
      })
      .catch((err) => onError(err instanceof Error ? err.message : String(err)));
    return () => {
      alive = false;
    };
  }, [onError]);

  const selectedProvider = providers.find((p) => p.id === form.provider);
  const baseUrlMode = selectedProvider?.base_url ?? null;
  const [tests, setTests] = useState<Record<string, TestState>>({});
  // Per-backend free-text prompt draft and its last answer, keyed by backend id.
  const [askDrafts, setAskDrafts] = useState<Record<string, string>>({});
  const [asks, setAsks] = useState<Record<string, AskState>>({});
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
      provider: form.provider as AiProvider,
      model: form.model.trim(),
    };
    // base_url is sent when the provider requires it, or when it is an optional
    // override the operator actually filled in (e.g. a Bedrock region host).
    if (baseUrlMode === "required") {
      backend.base_url = form.base_url.trim();
    } else if (baseUrlMode === "optional" && form.base_url.trim().length > 0) {
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
          ? { phase: "ok", latencyMs: result.latency_ms, reply: result.text }
          : { phase: "error", latencyMs: result.latency_ms, error: result.error },
      }));
      if (result.ok) {
        // The probe sends "ping"; the model's one-word reply proves a real
        // round-trip (not just connectivity), so surface it in the log too.
        const reply = result.text !== undefined && result.text.length > 0 ? ` -- "${result.text}"` : "";
        appendCall("info", id, `backend ${id} ok in ${result.latency_ms} ms${reply}`);
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

  async function handleAsk(id: string): Promise<void> {
    const prompt = (askDrafts[id] ?? "").trim();
    if (prompt.length === 0) {
      // Empty input is blocked client-side: the Ask button is disabled too.
      return;
    }
    setAsks((prev) => ({ ...prev, [id]: { phase: "asking" } }));
    try {
      const result = await testAiBackend(id, prompt);
      if (result.ok) {
        const text = result.text ?? "";
        setAsks((prev) => ({
          ...prev,
          [id]: { phase: "ok", latencyMs: result.latency_ms, text },
        }));
        // Surface the full exchange in the "Provider calls" console: the prompt
        // sent and the model's answer, so the operator reads responses there too.
        appendCall("info", id, `ask> ${prompt}`);
        appendCall("info", id, `${text} (${result.latency_ms} ms)`);
      } else {
        setAsks((prev) => ({
          ...prev,
          [id]: { phase: "error", latencyMs: result.latency_ms, error: result.error },
        }));
        appendCall(
          "error",
          id,
          `backend ${id} ask failed in ${result.latency_ms} ms: ${result.error}`,
        );
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setAsks((prev) => ({
        ...prev,
        [id]: { phase: "error", latencyMs: 0, error: message },
      }));
      appendCall("error", id, `backend ${id} ask failed: ${message}`);
    }
  }

  return (
    <section className="agents-backends">
      <h2>AI backends (the AI behind agents)</h2>
      <p className="agents-backends-note">
        Each backend pins a provider and model. Set an API key per backend
        below (write-only: the console sends it but never reads it back) or
        leave it unset to fall back to the provider env var at run time (R8).
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
                <td className="agents-key-cell">
                  <KeyCell
                    backend={backend}
                    draft={keyDrafts[backend.id] ?? ""}
                    onDraftChange={(value) =>
                      setKeyDrafts((prev) => ({ ...prev, [backend.id]: value }))
                    }
                    onSave={() => void handleSaveKey(backend.id)}
                    onRemove={() => void handleRemoveKey(backend.id)}
                    saved={savedHints[backend.id] === true}
                  />
                </td>
                <td>
                  <div className="agents-probe">
                    <div className="agents-probe-row">
                      <button
                        type="button"
                        className="agents-btn"
                        disabled={tests[backend.id]?.phase === "testing"}
                        onClick={() => void handleTest(backend.id)}
                      >
                        Test
                      </button>
                      <TestCell state={tests[backend.id]} />
                    </div>
                    <span className="agents-key-hint">
                      Uses the stored key, or the provider env var.
                    </span>
                  </div>
                  <AskCell
                    id={backend.id}
                    state={asks[backend.id]}
                    draft={askDrafts[backend.id] ?? ""}
                    onDraftChange={(value) =>
                      setAskDrafts((prev) => ({ ...prev, [backend.id]: value }))
                    }
                    onAsk={() => void handleAsk(backend.id)}
                  />
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
            onChange={(e) => setForm((p) => ({ ...p, provider: e.target.value }))}
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id}
              </option>
            ))}
          </select>
          <span className="agents-key-hint">{keyHintFor(selectedProvider)}</span>
        </div>
        {baseUrlMode !== null && (
          <div className="agents-form-row">
            <label htmlFor="backend-base-url">
              {baseUrlMode === "optional" ? "Base URL (optional)" : "Base URL"}
            </label>
            <input
              id="backend-base-url"
              type="text"
              placeholder={
                form.provider === "bedrock"
                  ? "https://bedrock-runtime.us-east-1.amazonaws.com"
                  : "http://localhost:11434/v1"
              }
              value={form.base_url}
              onChange={(e) => setForm((p) => ({ ...p, base_url: e.target.value }))}
              required={baseUrlMode === "required"}
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
