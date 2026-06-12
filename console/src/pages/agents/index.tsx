/**
 * Agents page: AI parametrization behind each registered agent.
 *
 * Lists agents (GET /config/agents), supports create / edit / delete, and
 * binds each agent to a configured AI backend (GET /config/ai-backends).
 * Each agent can be launched as a Lane B run (POST /runs); the live frames
 * stream into the reusable LogConsole below the table. No secret field is
 * ever displayed or submitted here (R8): credentials belong to the backend
 * proxies, never to this console.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  createAgent,
  deleteAgent,
  launchLaneB,
  listAgentActions,
  listAgents,
  listAiBackends,
  updateAgent,
} from "../../api/client";
import type { LaunchLaneBRequest } from "../../api/client";
import type { AgentAction, AgentConfig, AiBackend } from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import { LogConsole } from "../../components/LogConsole";
import type { LogLine } from "../../components/LogConsole";
import { useRunStream } from "../../hooks/useRunStream";
import type { RunFrame } from "../../hooks/useRunStream";
import AiBackendsPanel from "./AiBackendsPanel";
import "./agents.css";

/** Form state: every field as the raw string the user types. */
interface AgentFormValues {
  id: string;
  runtime: "lab" | "real";
  aiMode: "mock" | "real";
  principal: string;
  targetSystem: string;
  goal: string;
  actions: string[];
  aiBackendId: string;
}

const EMPTY_FORM: AgentFormValues = {
  id: "",
  runtime: "lab",
  aiMode: "mock",
  principal: "",
  targetSystem: "",
  goal: "",
  actions: [],
  aiBackendId: "",
};

/** Turn a list of chosen catalog actions into a deterministic mock scenario
 *  (one tool_call per action, then a final step). */
function scenarioFromActions(actions: string[]): Array<Record<string, unknown>> {
  const steps: Array<Record<string, unknown>> = actions.map((action) => ({
    kind: "tool_call",
    tool_name: action,
    tool_args: { resource: "acme/x" },
  }));
  steps.push({ kind: "final", text: "done" });
  return steps;
}

/** Build the API payload from the form; empty optional fields are omitted.
 *  The chosen catalog actions drive both capability_scope and the mock scenario. */
function toAgentConfig(values: AgentFormValues, id: string): AgentConfig {
  return {
    id,
    runtime: values.runtime,
    ai_mode: values.aiMode,
    principal: values.principal.trim() || undefined,
    target_system: values.targetSystem.trim() || undefined,
    goal: values.goal.trim() || undefined,
    capability_scope: values.actions,
    scenario: scenarioFromActions(values.actions),
    ai_backend_id: values.aiBackendId || undefined,
  };
}

/** Load an existing agent into the form for editing. */
function toFormValues(agent: AgentConfig): AgentFormValues {
  return {
    id: agent.id,
    runtime: agent.runtime,
    aiMode: agent.ai_mode ?? (agent.ai_backend_id ? "real" : "mock"),
    principal: agent.principal ?? "",
    targetSystem: agent.target_system ?? "",
    goal: agent.goal ?? "",
    actions: agent.capability_scope ?? [],
    aiBackendId: agent.ai_backend_id ?? "",
  };
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Compact one-line summary of a streamed lane_b frame. */
function frameText(frame: RunFrame): string {
  const d = frame.data;
  switch (frame.type) {
    case "start":
      return `start (kind=${String(d.kind ?? "")})`;
    case "step": {
      const action = d.action as Record<string, unknown> | undefined;
      const at = action
        ? `${String(action.action_type)}@${String(action.target_system)}`
        : "(no action)";
      return `step #${String(d.index ?? "")}: ${at}`;
    }
    case "result": {
      const actions = (d.actions as unknown[] | undefined) ?? [];
      return `result: ${actions.length} action(s) recorded`;
    }
    case "error":
      return `error: ${String(d.message ?? "")}`;
    case "end":
      return `end (status=${String(d.status ?? "")})`;
    default:
      return frame.type;
  }
}

/** Map one streamed run frame to a displayable log line. */
function frameToLogLine(frame: RunFrame, source: string): LogLine {
  const failed = frame.type === "error" || frame.data.error !== undefined;
  return {
    seq: frame.seq,
    level: failed ? "error" : "info",
    source,
    text: frameText(frame),
  };
}

/** Mock brain when declared, or (legacy records) when no backend is bound. */
function isMockAgent(agent: AgentConfig): boolean {
  return agent.ai_mode === "mock" || (agent.ai_mode === undefined && !agent.ai_backend_id);
}

export default function AgentsPage(): JSX.Element {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [backends, setBackends] = useState<AiBackend[]>([]);
  const [catalog, setCatalog] = useState<AgentAction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // null means the form is in create mode; otherwise the id being edited.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<AgentFormValues>(EMPTY_FORM);
  const stream = useRunStream();
  // Agent id of the current run; labels every line of the run log.
  const [runSource, setRunSource] = useState("run");

  const runLines = useMemo(() => {
    const lines = stream.frames.map((frame) => frameToLogLine(frame, runSource));
    if (stream.error !== null) {
      lines.push({
        seq: (stream.frames[stream.frames.length - 1]?.seq ?? 0) + 1,
        level: "error",
        source: runSource,
        text: stream.error,
      });
    }
    return lines;
  }, [stream.frames, stream.error, runSource]);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const [agentList, backendList, actionList] = await Promise.all([
        listAgents(),
        listAiBackends(),
        listAgentActions(),
      ]);
      setAgents(agentList);
      setBackends(backendList);
      setCatalog(actionList);
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

  function toggleAction(action: string): void {
    setForm((prev) => ({
      ...prev,
      actions: prev.actions.includes(action)
        ? prev.actions.filter((a) => a !== action)
        : [...prev.actions, action],
    }));
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

  async function handleRun(agent: AgentConfig): Promise<void> {
    setRunSource(agent.id);
    const body: LaunchLaneBRequest = { agent_id: agent.id };
    if (isMockAgent(agent) && agent.scenario !== undefined) {
      // A mock agent runs its stored scenario; a real-AI agent uses its
      // bound ai_backend on the server side (key from env, R8).
      body.stub_script = agent.scenario;
    }
    await stream.start(() => launchLaneB(body));
  }

  // Distinct target systems offered by the catalog, and the actions of the
  // currently selected system (the picker is scoped to one system).
  const catalogSystems = Array.from(
    new Set(catalog.map((a) => a.target_system)),
  ).sort();
  const scopedActions = catalog.filter((a) => a.target_system === form.targetSystem);

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
                      className="agents-btn agents-btn-primary"
                      disabled={stream.running}
                      onClick={() => void handleRun(agent)}
                    >
                      Run
                    </button>
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

      <section className="agents-run-log">
        {stream.runId !== null && (
          <p className="agents-run-status">
            run {stream.runId} -- {stream.status}
          </p>
        )}
        <LogConsole title="Run log" lines={runLines} />
      </section>

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
          <label htmlFor="agent-runtime">Cible (en face)</label>
          <select
            id="agent-runtime"
            value={form.runtime}
            onChange={(e) =>
              setField("runtime", e.target.value === "real" ? "real" : "lab")
            }
          >
            <option value="lab">Plateforme simulee (lab)</option>
            <option value="real">Serveur reel</option>
          </select>
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-ai-mode">IA derriere</label>
          <select
            id="agent-ai-mode"
            value={form.aiMode}
            onChange={(e) =>
              setField("aiMode", e.target.value === "real" ? "real" : "mock")
            }
          >
            <option value="mock">Mock (scenario scripte)</option>
            <option value="real">IA reelle (ai_backend)</option>
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
          <label htmlFor="agent-target-system">Target system (en face)</label>
          <select
            id="agent-target-system"
            value={form.targetSystem}
            onChange={(e) => setField("targetSystem", e.target.value)}
          >
            <option value="">(choisir un systeme)</option>
            {catalogSystems.map((sys) => (
              <option key={sys} value={sys}>
                {sys}
              </option>
            ))}
          </select>
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

        <fieldset className="agents-actions-picker">
          <legend>
            Actions de l'agent (catalogue {form.targetSystem || "..."}) -- ce que l'agent fait
            {form.actions.length > 0 ? ` (${form.actions.length})` : ""}
          </legend>
          <p className="agents-backends-note">
            Coche les actions du catalogue du systeme cible. Elles definissent le
            scope ET le scenario mock (1 action = 1 etape, dans l'ordre coche).
          </p>
          {form.targetSystem === "" ? (
            <p className="agents-empty">Choisis d'abord un target system.</p>
          ) : scopedActions.length === 0 ? (
            <p className="agents-empty">Aucune action pour {form.targetSystem}.</p>
          ) : (
            scopedActions.map((a) => (
              <label key={a.action} className="agents-action-row">
                <input
                  type="checkbox"
                  checked={form.actions.includes(a.action)}
                  onChange={() => toggleAction(a.action)}
                />
                <code>{a.action}</code>
                <span className={`pill pill-${a.kind}`}>{a.kind}</span>
                <span className="agents-action-desc">{a.description}</span>
              </label>
            ))
          )}
        </fieldset>

        <div className="agents-form-row">
          <label htmlFor="agent-ai-backend">
            AI backend {form.aiMode === "real" ? "(requis)" : "(si IA reelle)"}
          </label>
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

      <AiBackendsPanel
        backends={backends}
        onChanged={refresh}
        onError={setError}
      />
    </div>
  );
}
