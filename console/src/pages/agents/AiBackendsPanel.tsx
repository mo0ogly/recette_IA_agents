/**
 * AI-backends panel: list / create / delete the AI behind agents.
 *
 * Extracted from the Agents page to keep one responsibility per file. Provider
 * + model only -- the provider key is never stored here, it is resolved from
 * the environment at run time (R8).
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { createAiBackend, deleteAiBackend } from "../../api/client";
import type { AiBackend } from "../../types/platform";

export interface AiBackendsPanelProps {
  backends: AiBackend[];
  onChanged: () => void | Promise<void>;
  onError: (message: string) => void;
}

const EMPTY = { id: "", provider: "", model: "" };

export default function AiBackendsPanel(props: AiBackendsPanelProps): JSX.Element {
  const { backends, onChanged, onError } = props;
  const [form, setForm] = useState(EMPTY);

  async function handleCreate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const id = form.id.trim();
    if (id.length === 0) {
      onError("AI backend id is required.");
      return;
    }
    try {
      await createAiBackend({
        id,
        provider: form.provider.trim(),
        model: form.model.trim(),
      });
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
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {backends.length === 0 ? (
            <tr>
              <td colSpan={4} className="agents-empty">
                No AI backends configured.
              </td>
            </tr>
          ) : (
            backends.map((backend) => (
              <tr key={backend.id}>
                <td>{backend.id}</td>
                <td>{backend.provider}</td>
                <td>{backend.model}</td>
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
          <input
            id="backend-provider"
            type="text"
            placeholder="anthropic, openai, stub, ..."
            value={form.provider}
            onChange={(e) => setForm((p) => ({ ...p, provider: e.target.value }))}
          />
        </div>
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
