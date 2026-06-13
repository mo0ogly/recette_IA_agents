/**
 * Dashboard -- the control board of the agent recette bench.
 *
 * One row per configured agent showing, at a glance, the two mock/real axes
 * and the live status:
 *   - IA      : real AI (bound ai_backend) vs mock (scripted scenario)
 *   - Cible   : real server vs simulated platform (lab), from runtime
 *   - Statut  : actif (a run is pending/running) vs inactif, with the last
 *               run outcome (completed/failed/stopped)
 * Launch and stop happen here; status is polled from GET /runs.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  launchLaneB,
  listAgents,
  listRuns,
  stopRun,
} from "../../api/client";
import type { AgentConfig, RunSummary } from "../../types/platform";
import { isRealAi, isRealTarget } from "../../lib/aiBackend";
import PageHelp from "../../components/help/PageHelp";
import "./dashboard.css";

const POLL_MS = 2000;
const ACTIVE = new Set(["pending", "running"]);

/** Fallback mock scenario when an agent declares no scenario of its own. */
const DEFAULT_SCENARIO = [
  { kind: "tool_call", tool_name: "read_repo", tool_args: { resource: "acme/x" } },
  { kind: "final", text: "done" },
];

interface AgentRow {
  agent: AgentConfig;
  status: string; // "" when never run
  runId: string | null;
}

export default function DashboardPage(): JSX.Element {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const loadAgents = useCallback(async () => {
    try {
      setAgents(await listAgents());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      setRuns(await listRuns());
    } catch {
      // transient; keep last known runs
    }
  }, []);

  useEffect(() => {
    void loadAgents();
    void poll();
    timer.current = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      if (timer.current !== null) {
        window.clearInterval(timer.current);
      }
    };
  }, [loadAgents, poll]);

  // Latest run per agent (runs come newest-first from the API).
  const rowFor = (agent: AgentConfig): AgentRow => {
    const latest = runs.find((r) => r.agent_id === agent.id);
    return { agent, status: latest?.status ?? "", runId: latest?.id ?? null };
  };
  const rows = agents.map(rowFor);

  const launch = useCallback(
    async (agent: AgentConfig) => {
      setError(null);
      try {
        if (isRealAi(agent)) {
          await launchLaneB({ agent_id: agent.id });
        } else {
          const scenario = (agent.scenario && agent.scenario.length > 0
            ? agent.scenario
            : DEFAULT_SCENARIO) as Array<Record<string, unknown>>;
          await launchLaneB({ agent_id: agent.id, stub_script: scenario });
        }
        await poll();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [poll],
  );

  const stop = useCallback(
    async (runId: string) => {
      try {
        await stopRun(runId);
        await poll();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [poll],
  );

  const activeCount = rows.filter((r) => ACTIVE.has(r.status)).length;
  const realAiCount = agents.filter(isRealAi).length;
  const realTargetCount = agents.filter(isRealTarget).length;

  return (
    <div>
      <div className="page-head">
        <h1>Tableau de bord -- agents de recette</h1>
        <PageHelp topic="dashboard" />
      </div>

      {error !== null && (
        <div className="dash-error" role="alert">
          {error}
        </div>
      )}

      <div className="dash-summary">
        <div className="dash-card">
          <span className="dash-num">{agents.length}</span>
          <span className="dash-label">agents</span>
        </div>
        <div className="dash-card">
          <span className="dash-num dash-num-active">{activeCount}</span>
          <span className="dash-label">actifs</span>
        </div>
        <div className="dash-card">
          <span className="dash-num">{realAiCount}</span>
          <span className="dash-label">IA reelle</span>
        </div>
        <div className="dash-card">
          <span className="dash-num">{agents.length - realAiCount}</span>
          <span className="dash-label">IA mock</span>
        </div>
        <div className="dash-card">
          <span className="dash-num">{realTargetCount}</span>
          <span className="dash-label">cible reelle</span>
        </div>
        <div className="dash-card">
          <span className="dash-num">{agents.length - realTargetCount}</span>
          <span className="dash-label">cible simulee</span>
        </div>
      </div>

      <table className="dash-table">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Cible</th>
            <th>IA</th>
            <th>En face (cible)</th>
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {agents.length === 0 ? (
            <tr>
              <td colSpan={6} className="dash-empty">
                Aucun agent. Cree-en un dans l'onglet Agents.
              </td>
            </tr>
          ) : (
            rows.map(({ agent, status, runId }) => {
              const active = ACTIVE.has(status);
              return (
                <tr key={agent.id}>
                  <td className="dash-agent">
                    <strong>{agent.id}</strong>
                    <div className="dash-goal">{agent.goal ?? ""}</div>
                  </td>
                  <td>{agent.target_system ?? "?"}</td>
                  <td>
                    <span className={`pill ${isRealAi(agent) ? "pill-ok" : "pill-mock"}`}>
                      {isRealAi(agent) ? "IA reelle" : "Mock"}
                    </span>
                  </td>
                  <td>
                    <span className={`pill ${isRealTarget(agent) ? "pill-warn" : "pill-mock"}`}>
                      {isRealTarget(agent) ? "Reelle" : "Simulee (lab)"}
                    </span>
                  </td>
                  <td>
                    <span className={`dot dot-${active ? "on" : "off"}`} />
                    {active ? "actif" : status === "" ? "inactif" : status}
                  </td>
                  <td>
                    {active && runId !== null ? (
                      <button
                        type="button"
                        className="dash-stop"
                        onClick={() => void stop(runId)}
                      >
                        Arreter
                      </button>
                    ) : (
                      <button type="button" onClick={() => void launch(agent)}>
                        Lancer
                      </button>
                    )}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
      <p className="dash-hint">
        Statut rafraichi toutes les {POLL_MS / 1000}s. Pour le flux d'actions
        detaille d'un lancement, voir l'onglet Cockpit.
      </p>
    </div>
  );
}
