/**
 * Presentational agents table for the Agents page Configuration tab. Renders
 * the agent rows and per-row actions; all behaviour is delegated to callbacks
 * so the orchestrator owns the state.
 */

import type { AgentConfig, RunSummary } from "../../types/platform";
import EyeIcon from "../../components/EyeIcon";
import { voyantFor } from "../../lib/runStatus";

interface AgentsTableProps {
  agents: AgentConfig[];
  loaded: boolean;
  runDisabled: boolean;
  latestRun: (agentId: string) => RunSummary | undefined;
  onView: (agent: AgentConfig) => void;
  onRun: (agent: AgentConfig) => void;
  onPrecise: (agent: AgentConfig) => void;
  onExplain: (agent: AgentConfig) => void;
  onEdit: (agent: AgentConfig) => void;
  onDelete: (agentId: string) => void;
}

export default function AgentsTable({
  agents,
  loaded,
  runDisabled,
  latestRun,
  onView,
  onRun,
  onPrecise,
  onExplain,
  onEdit,
  onDelete,
}: AgentsTableProps): JSX.Element {
  return (
    <table className="agents-table">
      <thead>
        <tr>
          <th>Id</th>
          <th>Runtime</th>
          <th>Target</th>
          <th>Goal</th>
          <th>AI backend</th>
          <th>Capability scope</th>
          <th>Cadence</th>
          <th>Statut</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {loaded && agents.length === 0 ? (
          <tr>
            <td colSpan={9} className="agents-empty">
              No agents configured.
            </td>
          </tr>
        ) : (
          agents.map((agent) => {
            const run = latestRun(agent.id);
            const v = voyantFor(run?.status ?? "");
            return (
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
                  {agent.pace_ms !== undefined ? (
                    <span className="agents-pace">pace {agent.pace_ms}ms</span>
                  ) : (
                    ""
                  )}
                </td>
                <td>
                  <span className={`voyant ${v.cls}`}>
                    <span className="voyant-dot" />
                    {v.label}
                  </span>
                </td>
                <td>
                  <div className="agents-form-actions">
                    <button
                      type="button"
                      className="agents-btn"
                      title={
                        run ? "Voir le run de l'agent" : "Aucun run -- lance l'agent d'abord"
                      }
                      aria-label={`Voir le run de ${agent.id}`}
                      disabled={run === undefined}
                      onClick={() => onView(agent)}
                    >
                      <EyeIcon />
                    </button>
                    <button
                      type="button"
                      className="agents-btn agents-btn-primary"
                      disabled={runDisabled}
                      onClick={() => onRun(agent)}
                    >
                      Run
                    </button>
                    <button
                      type="button"
                      className="agents-btn"
                      aria-label={`Lancer precis pour ${agent.id}`}
                      title="Composer une instance precise (actions + ressources + profil) et juger le run"
                      onClick={() => onPrecise(agent)}
                    >
                      Lancer precis
                    </button>
                    <button
                      type="button"
                      className="agents-btn"
                      aria-label={`Expliquer ${agent.id}`}
                      title="Voir la fiche de l'agent (identite, capacites, scenario, recette)"
                      onClick={() => onExplain(agent)}
                    >
                      Expliquer
                    </button>
                    <button type="button" className="agents-btn" onClick={() => onEdit(agent)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="agents-btn agents-btn-danger"
                      onClick={() => onDelete(agent.id)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            );
          })
        )}
      </tbody>
    </table>
  );
}
