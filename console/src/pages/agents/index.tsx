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
  listRuns,
  listSubjects,
  purgeRuns,
  updateAgent,
} from "../../api/client";
import type { CorpusSubject } from "../../api/client";
import type { LaunchLaneBRequest } from "../../api/client";
import type {
  AgentAction,
  AgentConfig,
  AiBackend,
  RunSummary,
} from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import { LogConsole } from "../../components/LogConsole";
import type { LogLine } from "../../components/LogConsole";
import { useRunStream } from "../../hooks/useRunStream";
import type { RunFrame } from "../../hooks/useRunStream";
import AgentRunModal from "../../components/AgentRunModal";
import PreciseLaunchModal from "../../components/PreciseLaunchModal";
import AgentExplainModal from "../../components/AgentExplainModal";
import EyeIcon from "../../components/EyeIcon";
import { voyantFor } from "../../lib/runStatus";
import CockpitPage from "../cockpit";
import CorpusPage from "../corpus";
import "./agents.css";

/** The two views of the Agents page: agent CRUD, or the launch/debug cockpit. */
type AgentsTab = "config" | "corpus" | "cockpit" | "run";

/**
 * One plain-language line per tab so nobody confuses the "answer key" (Corpus)
 * with the "exam" (Cockpit/runtime). School metaphor: Corpus = the marked
 * answer key (read-only), Cockpit = sit an agent for the exam, Run log = its
 * paper. Detail lives in the page help + docs.
 */
const TAB_NOTES: Record<AgentsTab, string> = {
  config: "L'atelier : on cree et regle les agents ici. Rien ne tourne.",
  corpus:
    "Le corrige : la bonne reponse attendue pour chaque agent. Lecture seule, on ne lance rien.",
  cockpit:
    "L'examen : on lance un agent, il agit pour de vrai et produit sa copie (ce qu'il a FAIT).",
  run: "La copie : ce que l'agent vient de faire, etape par etape.",
};

interface Viewing {
  agentId: string;
  runId: string | null;
  status: string;
}

const RUNS_POLL_MS = 2000;

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
  corpusSubjectId: string;
  // Full properties (previously invisible in the form).
  role: string;
  model: string;
  systemPrompt: string;
  scenarioJson: string;
  gtDetectable: boolean;
  gtVerdict: "" | "correct" | "incorrect";
  gtIdentity: string;
  gtIdentityDim: boolean;
  gtCapabilitiesDim: boolean;
  gtPolicyDim: boolean;
  gtBehaviorDim: boolean;
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
  corpusSubjectId: "",
  role: "",
  model: "",
  systemPrompt: "",
  scenarioJson: "",
  gtDetectable: false,
  gtVerdict: "",
  gtIdentity: "",
  gtIdentityDim: false,
  gtCapabilitiesDim: false,
  gtPolicyDim: false,
  gtBehaviorDim: false,
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

/** Build the ground_truth block from the form, or undefined if nothing set. */
function groundTruthFrom(values: AgentFormValues): AgentConfig["ground_truth"] {
  const anySet =
    values.gtDetectable ||
    values.gtVerdict !== "" ||
    values.gtIdentity.trim() !== "" ||
    values.gtIdentityDim ||
    values.gtCapabilitiesDim ||
    values.gtPolicyDim ||
    values.gtBehaviorDim;
  if (!anySet) {
    return undefined;
  }
  return {
    detectable: values.gtDetectable,
    expected_verdict: values.gtVerdict === "" ? undefined : values.gtVerdict,
    expected_identity: values.gtIdentity.trim() || undefined,
    dimensions: {
      identity: values.gtIdentityDim,
      capabilities: values.gtCapabilitiesDim,
      policy: values.gtPolicyDim,
      behavior: values.gtBehaviorDim,
    },
  };
}

/** Build the API payload from the form; empty optional fields are omitted.
 *  A raw scenario JSON (if valid) wins over the action-derived mock scenario,
 *  so a custom multi-step scenario is preserved through an edit. */
function toAgentConfig(values: AgentFormValues, id: string): AgentConfig {
  let scenario = scenarioFromActions(values.actions);
  const raw = values.scenarioJson.trim();
  if (raw !== "") {
    const parsed: unknown = JSON.parse(raw); // throws -> caught by the caller
    if (!Array.isArray(parsed)) {
      throw new Error("scenario must be a JSON array");
    }
    scenario = parsed as Array<Record<string, unknown>>;
  }
  return {
    id,
    runtime: values.runtime,
    ai_mode: values.aiMode,
    principal: values.principal.trim() || undefined,
    target_system: values.targetSystem.trim() || undefined,
    goal: values.goal.trim() || undefined,
    capability_scope: values.actions,
    scenario,
    ai_backend_id: values.aiBackendId || undefined,
    corpus_subject_id: values.corpusSubjectId || undefined,
    role: values.role.trim() || undefined,
    model: values.model.trim() || undefined,
    system_prompt: values.systemPrompt.trim() || undefined,
    ground_truth: groundTruthFrom(values),
  };
}

/** Load an existing agent into the form for editing. */
function toFormValues(agent: AgentConfig): AgentFormValues {
  const gt = agent.ground_truth ?? {};
  const dims = gt.dimensions ?? {};
  return {
    id: agent.id,
    runtime: agent.runtime,
    aiMode: agent.ai_mode ?? (agent.ai_backend_id ? "real" : "mock"),
    principal: agent.principal ?? "",
    targetSystem: agent.target_system ?? "",
    goal: agent.goal ?? "",
    actions: agent.capability_scope ?? [],
    aiBackendId: agent.ai_backend_id ?? "",
    corpusSubjectId: agent.corpus_subject_id ?? "",
    role: agent.role ?? "",
    model: agent.model ?? "",
    systemPrompt: agent.system_prompt ?? "",
    scenarioJson: agent.scenario ? JSON.stringify(agent.scenario, null, 2) : "",
    gtDetectable: gt.detectable ?? false,
    gtVerdict: gt.expected_verdict ?? "",
    gtIdentity: gt.expected_identity ?? "",
    gtIdentityDim: dims.identity ?? false,
    gtCapabilitiesDim: dims.capabilities ?? false,
    gtPolicyDim: dims.policy ?? false,
    gtBehaviorDim: dims.behavior ?? false,
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
  const [activeTab, setActiveTab] = useState<AgentsTab>("config");
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [backends, setBackends] = useState<AiBackend[]>([]);
  const [catalog, setCatalog] = useState<AgentAction[]>([]);
  const [subjects, setSubjects] = useState<CorpusSubject[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // null means the form is in create mode; otherwise the id being edited.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<AgentFormValues>(EMPTY_FORM);
  const stream = useRunStream();
  // Agent id of the current run; labels every line of the run log.
  const [runSource, setRunSource] = useState("run");
  // Latest run per agent (for the status light) + the eye-modal target.
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [viewing, setViewing] = useState<Viewing | null>(null);
  const [precise, setPrecise] = useState<AgentConfig | null>(null);
  const [explaining, setExplaining] = useState<AgentConfig | null>(null);

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
      const [agentList, backendList, actionList, subjectListing] = await Promise.all([
        listAgents(),
        listAiBackends(),
        listAgentActions(),
        listSubjects().catch(() => ({ count: 0, families: {}, subjects: [] })),
      ]);
      setAgents(agentList);
      setBackends(backendList);
      setCatalog(actionList);
      setSubjects(subjectListing.subjects);
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

  const pollRuns = useCallback(async (): Promise<void> => {
    try {
      setRuns(await listRuns());
    } catch {
      // transient; keep last known runs
    }
  }, []);

  useEffect(() => {
    void pollRuns();
    const timer = window.setInterval(() => void pollRuns(), RUNS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [pollRuns]);

  /** Latest run (runs are newest-first) of an agent, for its status light. */
  const latestRun = (agentId: string): RunSummary | undefined =>
    runs.find((r) => r.agent_id === agentId);

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

      <div className="agents-tabs" role="tablist" aria-label="Vue des agents">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "config"}
          className={activeTab === "config" ? "agents-tab agents-tab-active" : "agents-tab"}
          onClick={() => setActiveTab("config")}
        >
          Configuration
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "corpus"}
          className={activeTab === "corpus" ? "agents-tab agents-tab-active" : "agents-tab"}
          onClick={() => setActiveTab("corpus")}
        >
          Corpus
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "cockpit"}
          className={activeTab === "cockpit" ? "agents-tab agents-tab-active" : "agents-tab"}
          onClick={() => setActiveTab("cockpit")}
        >
          Cockpit -- lancer &amp; debug
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "run"}
          className={activeTab === "run" ? "agents-tab agents-tab-active" : "agents-tab"}
          onClick={() => setActiveTab("run")}
        >
          Run log
        </button>
      </div>

      <p className="agents-tab-note" data-testid="agents-tab-note">
        {TAB_NOTES[activeTab]}
      </p>

      {activeTab === "corpus" && <CorpusPage />}

      {activeTab === "cockpit" && <CockpitPage />}

      {activeTab === "run" && (
        <section className="agents-run-log">
          {stream.runId !== null ? (
            <p className="agents-run-status">
              run {stream.runId} -- {stream.status}
            </p>
          ) : (
            <p className="agents-run-empty" data-testid="agents-run-empty">
              Vide tant qu'aucun run n'est lance. Va dans{" "}
              <strong>Configuration</strong> et clique <em>Run</em> sur une ligne
              d'agent : sa copie (start -&gt; step -&gt; result -&gt; end)
              s'affiche ici. Le <strong>Cockpit</strong> a son propre flux live
              (separe de cet onglet).
            </p>
          )}
          <LogConsole title="Run log" lines={runLines} />
        </section>
      )}

      {activeTab === "config" && (
        <>
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
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {loaded && agents.length === 0 ? (
            <tr>
              <td colSpan={8} className="agents-empty">
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
                  {(() => {
                    const v = voyantFor(latestRun(agent.id)?.status ?? "");
                    return (
                      <span className={`voyant ${v.cls}`}>
                        <span className="voyant-dot" />
                        {v.label}
                      </span>
                    );
                  })()}
                </td>
                <td>
                  <div className="agents-form-actions">
                    <button
                      type="button"
                      className="agents-btn"
                      title={
                        latestRun(agent.id)
                          ? "Voir le run de l'agent"
                          : "Aucun run -- lance l'agent d'abord"
                      }
                      aria-label={`Voir le run de ${agent.id}`}
                      disabled={latestRun(agent.id) === undefined}
                      onClick={() =>
                        setViewing({
                          agentId: agent.id,
                          runId: latestRun(agent.id)?.id ?? null,
                          status: latestRun(agent.id)?.status ?? "",
                        })
                      }
                    >
                      <EyeIcon />
                    </button>
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
                      aria-label={`Lancer precis pour ${agent.id}`}
                      title="Composer une instance precise (actions + ressources + profil) et juger le run"
                      onClick={() => setPrecise(agent)}
                    >
                      Lancer precis
                    </button>
                    <button
                      type="button"
                      className="agents-btn"
                      aria-label={`Expliquer ${agent.id}`}
                      title="Voir la fiche de l'agent (identite, capacites, scenario, recette)"
                      onClick={() => setExplaining(agent)}
                    >
                      Expliquer
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

        <div className="agents-form-row">
          <label htmlFor="agent-role">Role</label>
          <input
            id="agent-role"
            type="text"
            value={form.role}
            placeholder="e.g. finance_admin"
            onChange={(e) => setField("role", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-model">Model</label>
          <input
            id="agent-model"
            type="text"
            value={form.model}
            placeholder="e.g. llama-3.3-70b-versatile"
            onChange={(e) => setField("model", e.target.value)}
          />
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-system-prompt">System prompt</label>
          <textarea
            id="agent-system-prompt"
            rows={3}
            value={form.systemPrompt}
            placeholder="Instruction donnee a l'IA reelle (mode real)"
            onChange={(e) => setField("systemPrompt", e.target.value)}
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

        <div className="agents-form-row">
          <label htmlFor="agent-corpus-subject">Sujet corpus (ground-truth lie)</label>
          <select
            id="agent-corpus-subject"
            value={form.corpusSubjectId}
            onChange={(e) => setField("corpusSubjectId", e.target.value)}
          >
            <option value="">(aucun -- pas de ground-truth)</option>
            {subjects.map((s) => (
              <option key={s.agent_id} value={s.agent_id}>
                {s.agent_id} ({s.expected_verdict ?? "?"})
              </option>
            ))}
          </select>
        </div>

        <div className="agents-form-row">
          <label htmlFor="agent-scenario">Scenario (JSON, avance)</label>
          <textarea
            id="agent-scenario"
            rows={5}
            value={form.scenarioJson}
            placeholder="Vide = genere depuis les actions cochees. Sinon un tableau JSON d'etapes."
            onChange={(e) => setField("scenarioJson", e.target.value)}
          />
        </div>

        <fieldset className="agents-actions-picker">
          <legend>Ground-truth inline (verdict attendu sur les 4 dimensions)</legend>
          <label className="agents-action-row">
            <input
              type="checkbox"
              checked={form.gtDetectable}
              onChange={(e) => setField("gtDetectable", e.target.checked)}
            />
            detectable
          </label>
          <div className="agents-form-row">
            <label htmlFor="agent-gt-verdict">Verdict attendu</label>
            <select
              id="agent-gt-verdict"
              value={form.gtVerdict}
              onChange={(e) =>
                setField("gtVerdict", e.target.value as AgentFormValues["gtVerdict"])
              }
            >
              <option value="">(aucun)</option>
              <option value="correct">correct</option>
              <option value="incorrect">incorrect</option>
            </select>
          </div>
          <div className="agents-form-row">
            <label htmlFor="agent-gt-identity">Identite attendue</label>
            <input
              id="agent-gt-identity"
              type="text"
              value={form.gtIdentity}
              placeholder="e.g. bot@acme"
              onChange={(e) => setField("gtIdentity", e.target.value)}
            />
          </div>
          <label className="agents-action-row">
            <input
              type="checkbox"
              checked={form.gtIdentityDim}
              onChange={(e) => setField("gtIdentityDim", e.target.checked)}
            />
            dimension identity OK
          </label>
          <label className="agents-action-row">
            <input
              type="checkbox"
              checked={form.gtCapabilitiesDim}
              onChange={(e) => setField("gtCapabilitiesDim", e.target.checked)}
            />
            dimension capabilities OK
          </label>
          <label className="agents-action-row">
            <input
              type="checkbox"
              checked={form.gtPolicyDim}
              onChange={(e) => setField("gtPolicyDim", e.target.checked)}
            />
            dimension policy OK
          </label>
          <label className="agents-action-row">
            <input
              type="checkbox"
              checked={form.gtBehaviorDim}
              onChange={(e) => setField("gtBehaviorDim", e.target.checked)}
            />
            dimension behavior OK
          </label>
        </fieldset>

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

      <AgentRunModal
        open={viewing !== null}
        agentId={viewing?.agentId ?? ""}
        runId={viewing?.runId ?? null}
        status={viewing?.status ?? ""}
        runs={runs}
        onPurge={async (id) => {
          await purgeRuns(id);
          await pollRuns();
        }}
        onClose={() => setViewing(null)}
      />

      <PreciseLaunchModal
        open={precise !== null}
        agent={precise}
        onClose={() => {
          setPrecise(null);
          void pollRuns();
        }}
      />

      <AgentExplainModal
        open={explaining !== null}
        agent={explaining}
        onClose={() => setExplaining(null)}
      />
        </>
      )}
    </div>
  );
}
