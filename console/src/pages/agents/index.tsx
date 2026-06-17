/**
 * Agents page (orchestrator): AI parametrization behind each registered agent.
 *
 * Owns data fetch + top-level state; presentation is delegated to sibling
 * files under ./ (AgentsTable, AgentWizard) and pure logic to agentForm.ts /
 * agentRunLog.ts. Lists agents (GET /config/agents), supports create / edit /
 * delete via the wizard, binds each agent to a configured AI backend, and
 * launches a Lane B run (POST /runs) whose live frames stream into the
 * LogConsole. No secret field is ever displayed or submitted here (R8).
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
import { useRunStream } from "../../hooks/useRunStream";
import AgentRunModal from "../../components/AgentRunModal";
import PreciseLaunchModal from "../../components/PreciseLaunchModal";
import AgentExplainModal from "../../components/AgentExplainModal";
import CockpitPage from "../cockpit";
import CorpusPage from "../corpus";
import type { AgentFormValues } from "./agentForm";
import { EMPTY_FORM, errorMessage, toAgentConfig, toFormValues } from "./agentForm";
import { frameToLogLine, isMockAgent } from "./agentRunLog";
import AgentsTable from "./AgentsTable";
import AgentWizard from "./AgentWizard";
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

  function setField<K extends keyof AgentFormValues>(key: K, value: AgentFormValues[K]): void {
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
  const catalogSystems = Array.from(new Set(catalog.map((a) => a.target_system))).sort();
  const scopedActions = catalog.filter((a) => a.target_system === form.targetSystem);

  const TABS: Array<[AgentsTab, string]> = [
    ["config", "Configuration"],
    ["corpus", "Corpus"],
    ["cockpit", "Cockpit -- lancer & debug"],
    ["run", "Run log"],
  ];

  return (
    <div>
      <div className="page-head">
        <h1>Agents</h1>
        <PageHelp topic="agents" />
      </div>

      <div className="agents-tabs" role="tablist" aria-label="Vue des agents">
        {TABS.map(([tab, label]) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "agents-tab agents-tab-active" : "agents-tab"}
            onClick={() => setActiveTab(tab)}
          >
            {label}
          </button>
        ))}
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
              Vide tant qu'aucun run n'est lance. Va dans <strong>Configuration</strong> et clique{" "}
              <em>Run</em> sur une ligne d'agent : sa copie (start -&gt; step -&gt; result -&gt;
              end) s'affiche ici. Le <strong>Cockpit</strong> a son propre flux live (separe de cet
              onglet).
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

          <AgentsTable
            agents={agents}
            loaded={loaded}
            runDisabled={stream.running}
            latestRun={latestRun}
            onView={(agent) =>
              setViewing({
                agentId: agent.id,
                runId: latestRun(agent.id)?.id ?? null,
                status: latestRun(agent.id)?.status ?? "",
              })
            }
            onRun={(agent) => void handleRun(agent)}
            onPrecise={(agent) => setPrecise(agent)}
            onExplain={(agent) => setExplaining(agent)}
            onEdit={startEdit}
            onDelete={(id) => void handleDelete(id)}
          />

          <AgentWizard
            editingId={editingId}
            form={form}
            setField={setField}
            toggleAction={toggleAction}
            onSubmit={(e) => void handleSubmit(e)}
            onCancel={cancelEdit}
            catalogSystems={catalogSystems}
            scopedActions={scopedActions}
            backends={backends}
            subjects={subjects}
          />

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
