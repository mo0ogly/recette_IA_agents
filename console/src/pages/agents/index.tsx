/**
 * Agents page: AI parametrization behind each registered agent.
 *
 * Lists agents (GET /config/agents), supports create / edit / delete, and
 * binds each agent to a configured AI backend (GET /config/ai-backends).
 * No secret field is ever displayed or submitted here (R8): credentials
 * belong to the backend proxies, never to this console.
 */

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  createAgent,
  createAiBackend,
  deleteAgent,
  deleteAiBackend,
  listAgents,
  listAiBackends,
  updateAgent,
} from "../../api/client";
import type { AgentConfig, AiBackend } from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import "./agents.css";

/** Form state: every field as the raw string the user types. */
interface AgentFormValues {
  id: string;
  runtime: "lab" | "real";
  principal: string;
  targetSystem: string;
  goal: string;
  role: string;
  capabilityScope: string;
  systemPrompt: string;
  model: string;
  aiBackendId: string;
}

const EMPTY_FORM: AgentFormValues = {
  id: "",
  runtime: "lab",
  principal: "",
  targetSystem: "",
  goal: "",
  role: "",
  capabilityScope: "",
  systemPrompt: "",
  model: "",
  aiBackendId: "",
};

/** Parse the comma-separated capability scope into a clean string array. */
function parseCapabilityScope(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

/** Build the API payload from the form; empty optional fields are omitted. */
function toAgentConfig(values: AgentFormValues, id: string): AgentConfig {
  return {
    id,
    runtime: values.runtime,
    principal: values.principal.trim() || undefined,
    target_system: values.targetSystem.trim() || undefined,
    goal: values.goal.trim() || undefined,
    role: values.role.trim() || undefined,
    capability_scope: parseCapabilityScope(values.capabilityScope),
    system_prompt: values.systemPrompt.trim() || undefined,
    model: values.model.trim() || undefined,
    ai_backend_id: values.aiBackendId || undefined,
  };
}

/** Load an existing agent into the form for editing. */
function toFormValues(agent: AgentConfig): AgentFormValues {
  return {
    id: agent.id,
    runtime: agent.runtime,
    principal: agent.principal ?? "",
    targetSystem: agent.target_system ?? "",
    goal: agent.goal ?? "",
    role: agent.role ?? "",
    capabilityScope: (agent.capability_scope ?? []).join(", "),
    systemPrompt: agent.system_prompt ?? "",
    model: agent.model ?? "",
    aiBackendId: agent.ai_backend_id ?? "",
  };
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export default function AgentsPage(): JSX.Element {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [backends, setBackends] = useState<AiBackend[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // null means the form is in create mode; otherwise the id being edited.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<AgentFormValues>(EMPTY_FORM);
  // AI backend creation form (the AI behind an agent). No secret here (R8).
  const [backendForm, setBackendForm] = useState({ id: "", provider: "", model: "" });

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const [agentList, backendList] = await Promise.all([
        listAgents(),
        listAiBackends(),
      ]);
      setAgents(agentList);
      setBackends(backendList);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function setField<K extends keyof AgentFormValues>(
    key: K,
    value: AgentFormValues[K],
  ): void {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function startEdit(agent: AgentConfig): void {
    setEditingId(agent.id);
    setForm(toFormValues(agent));
  }

  function cancelEdit(): void {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const id = editingId ?? form.id.trim();
    if (id.length === 0) {
      setError("Agent id is required.");
      return;
    }
    try {
      const payload = toAgentConfig(form, id);
      if (editingId === null) {
        await createAgent(payload);
      } else {
        await updateAgent(editingId, payload);
      }
      cancelEdit();
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleCreateBackend(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const id = backendForm.id.trim();
    if (id.length === 0) {
      setError("AI backend id is required.");
      return;
    }
    try {
      await createAiBackend({
        id,
        provider: backendForm.provider.trim(),
        model: backendForm.model.trim(),
      });
      setBackendForm({ id: "", provider: "", model: "" });
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDeleteBackend(id: string): Promise<void> {
    if (!window.confirm(`Delete AI backend "${id}"?`)) {
      return;
    }
    try {
      await deleteAiBackend(id);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDelete(id: string): Promise<void> {
    if (!window.confirm(`Delete agent "${id}"?`)) {
      return;
    }
    try {
      await deleteAgent(id);
      if (editingId === id) {
        cancelEdit();
      }
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Agents</h1>
        <PageHelp topic="agents" />
      </div>

      {error !== null && (
        <div className="agents-error-banner" role="alert">
          {error}
        </div>
      )}

      <table className="agents-table">
        <thead>
          <tr>
            <th>Id</th>
            <th>Runtime</th>
            <th>Target</th>
            <th>Goal</th>
            <th>AI backend</th>
            <th>Capability scope</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {loaded && agents.length === 0 ? (
            <tr>
              <td colSpan={7} className="agents-empty">
                No agents configured.
              </td>
            </tr>
          ) : (
            agents.map((agent) => (
              <tr key={agent.id}>
                <td>{agent.id}</td>
                <td>
                  <span className="agents-runtime">{agent.runtime}</span>
                </td>
                <td>{agent.target_system ?? ""}</td>
                <td>{agent.goal ?? ""}</td>
                <td>{agent.ai_backend_id ?? ""}</td>
                <td>{(agent.capability_scope ?? []).join(", ")}</td>
                <td>
                  <div className="agents-form-actions">
                    <button
                      type="button"
                      className="agents-btn"
                      onClick={() => startEdit(agent)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="agents-btn agents-btn-danger"
                      onClick={() => void handleDelete(agent.id)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <form className="agents-form" onSubmit={(e) => void handleSubmit(e)}>
        <h2>{editingId === null ? "Create agent" : `Edit agent ${editingId}`}</h2>

        {editingId === null && (
          <div className="agents-form-row">
            <label htmlFor="agent-id">Id</label>
            <input
              id="agent-id"
              type="text"
              value={form.id}
              onChange={(e) => setField("id", e.target.value)}
              required
            />
          </div>
        )}

        <div className="agents-form-row">
          <label htmlFor="agent-runtime">Runtime</label>
          <select
            id="agent-runtime"
            value={form.runtime}
            onChange={(e) =>
              setField("runtime", e.target.value === "real" ? "real" : "lab")
            }
          >
            <option value="lab">lab</option>
            <option value="real">real</option>
          </select>
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-principal">Principal (identity)</label>
          <input
            id="agent-principal"
            type="text"
            value={form.principal}
            onChange={(e) => setField("principal", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-target-system">Target system</label>
          <input
            id="agent-target-system"
            type="text"
            placeholder="github, gitlab, ..."
            value={form.targetSystem}
            onChange={(e) => setField("targetSystem", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-goal">Goal</label>
          <input
            id="agent-goal"
            type="text"
            value={form.goal}
            onChange={(e) => setField("goal", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-role">Role (governance, optional)</label>
          <input
            id="agent-role"
            type="text"
            value={form.role}
            onChange={(e) => setField("role", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-capability-scope">
            Capability scope (comma-separated)
          </label>
          <input
            id="agent-capability-scope"
            type="text"
            value={form.capabilityScope}
            onChange={(e) => setField("capabilityScope", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-system-prompt">System prompt</label>
          <textarea
            id="agent-system-prompt"
            value={form.systemPrompt}
            onChange={(e) => setField("systemPrompt", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-model">Model</label>
          <input
            id="agent-model"
            type="text"
            value={form.model}
            onChange={(e) => setField("model", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-ai-backend">AI backend</label>
          <select
            id="agent-ai-backend"
            value={form.aiBackendId}
            onChange={(e) => setField("aiBackendId", e.target.value)}
          >
            <option value="">(none)</option>
            {backends.map((backend) => (
              <option key={backend.id} value={backend.id}>
                {backend.id} ({backend.provider} / {backend.model})
              </option>
            ))}
          </select>
        </div>

        <div className="agents-form-actions">
          <button type="submit" className="agents-btn agents-btn-primary">
            {editingId === null ? "Create" : "Save"}
          </button>
          {editingId !== null && (
            <button type="button" className="agents-btn" onClick={cancelEdit}>
              Cancel
            </button>
          )}
        </div>
      </form>

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
                      onClick={() => void handleDeleteBackend(backend.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        <form className="agents-form" onSubmit={(e) => void handleCreateBackend(e)}>
          <h2>Create AI backend</h2>
          <div className="agents-form-row">
            <label htmlFor="backend-id">Id</label>
            <input
              id="backend-id"
              type="text"
              value={backendForm.id}
              onChange={(e) => setBackendForm((p) => ({ ...p, id: e.target.value }))}
              required
            />
          </div>
          <div className="agents-form-row">
            <label htmlFor="backend-provider">Provider</label>
            <input
              id="backend-provider"
              type="text"
              placeholder="anthropic, openai, stub, ..."
              value={backendForm.provider}
              onChange={(e) => setBackendForm((p) => ({ ...p, provider: e.target.value }))}
            />
          </div>
          <div className="agents-form-row">
            <label htmlFor="backend-model">Model</label>
            <input
              id="backend-model"
              type="text"
              placeholder="claude-opus-4-8, ..."
              value={backendForm.model}
              onChange={(e) => setBackendForm((p) => ({ ...p, model: e.target.value }))}
            />
          </div>
          <div className="agents-form-actions">
            <button type="submit" className="agents-btn agents-btn-primary">
              Create backend
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
