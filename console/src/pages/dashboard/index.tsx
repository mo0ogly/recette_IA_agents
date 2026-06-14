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
  clearProxyTraces,
  launchLaneB,
  listAgents,
  listCampaigns,
  listRuns,
  purgeRuns,
  runCampaign,
  stopRun,
  submitRunVerdict,
} from "../../api/client";
import type { AgentConfig, Campaign, RunSummary } from "../../types/platform";
import { isRealAi, isRealTarget } from "../../lib/aiBackend";
import PageHelp from "../../components/help/PageHelp";
import AgentRunModal from "../../components/AgentRunModal";
import PreciseLaunchModal from "../../components/PreciseLaunchModal";
import AgentExplainModal from "../../components/AgentExplainModal";
import EyeIcon from "../../components/EyeIcon";
import { launchTally, voyantFor } from "../../lib/runStatus";
import "./dashboard.css";

interface Viewing {
  agentId: string;
  runId: string | null;
  status: string;
}

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
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [launching, setLaunching] = useState<Set<string>>(new Set());
  const [launchingCampaign, setLaunchingCampaign] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Viewing | null>(null);
  // A campaign (multi-agent) whose run is open in the campaign eye modal.
  const [campaignViewing, setCampaignViewing] = useState<{
    campaign: Campaign;
    runId: string | null;
    status: string;
  } | null>(null);
  const [precise, setPrecise] = useState<AgentConfig | null>(null);
  const [explaining, setExplaining] = useState<AgentConfig | null>(null);
  const timer = useRef<number | null>(null);
  // Runs already auto-submitted as verdicts, so each finished run is submitted
  // once. Seeded on the first poll so only runs that FINISH while the page is
  // open are submitted (no retroactive flood of historical runs).
  const submittedRef = useRef<Set<string>>(new Set());
  const seededRef = useRef(false);

  const loadAgents = useCallback(async () => {
    try {
      const [a, c] = await Promise.all([listAgents(), listCampaigns()]);
      setAgents(a);
      setCampaigns(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const rs = await listRuns();
      setRuns(rs);
      // Close the recette loop automatically: a run that just finished is
      // submitted as a verdict (POST /runs/{id}/submit-verdict), so /verdicts
      // reacts to launches. Agents without ground_truth judge to SKIP, never a
      // vacuous PASS. Best-effort: a submit failure never disturbs the board.
      const terminal = rs.filter((r) => r.id && r.agent_id && !ACTIVE.has(r.status));
      if (!seededRef.current) {
        terminal.forEach((r) => submittedRef.current.add(r.id));
        seededRef.current = true;
      } else {
        for (const r of terminal) {
          if (!submittedRef.current.has(r.id)) {
            submittedRef.current.add(r.id);
            void submitRunVerdict(r.id).catch(() => {});
          }
        }
      }
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
      // Instant visual feedback the click registered, before any network call:
      // a mock run completes in well under the poll interval, so without this
      // the only sign of a launch is a quiet status flip that is easy to miss.
      setLaunching((prev) => new Set(prev).add(agent.id));
      setNotice(`Lancement de ${agent.id}...`);
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
        setNotice(`Run lance pour ${agent.id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setNotice(null);
      } finally {
        setLaunching((prev) => {
          const next = new Set(prev);
          next.delete(agent.id);
          return next;
        });
      }
    },
    [poll],
  );

  const launchCampaign = useCallback(
    async (campaign: Campaign) => {
      setError(null);
      setLaunchingCampaign((prev) => new Set(prev).add(campaign.id));
      setNotice(`Lancement de la campagne ${campaign.id}...`);
      try {
        await runCampaign(campaign.id);
        await poll();
        setNotice(`Campagne ${campaign.id} lancee`);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setNotice(null);
      } finally {
        setLaunchingCampaign((prev) => {
          const next = new Set(prev);
          next.delete(campaign.id);
          return next;
        });
      }
    },
    [poll],
  );

  // Latest run for a campaign (runs come newest-first, matched on campaign_id).
  const campaignRun = (campaignId: string): RunSummary | undefined =>
    runs.find((r) => r.campaign_id === campaignId);
  const campaignStatus = (campaignId: string): string =>
    campaignRun(campaignId)?.status ?? "";

  const resetAll = useCallback(async () => {
    // Reset the ephemeral read-models only: finished runs (launch KPI) and the
    // proxy debug trace buffer. Active runs are preserved by the backend, and
    // the append-only audit log is NEVER touched (I1).
    if (!window.confirm("Reinitialiser tous les launches et logs (runs termines + traces proxy) ?")) {
      return;
    }
    setError(null);
    try {
      const { removed } = await purgeRuns();
      await clearProxyTraces();
      await poll();
      setNotice(`Reset: ${removed} run(s) et les traces proxy effaces`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [poll]);

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
  // Launch KPI over ALL runs (not just the latest per agent): successes vs
  // failures across the bench, so a flaky agent shows up even after a later
  // green run masks it in the per-agent status column.
  const tally = launchTally(runs);

  return (
    <div>
      <div className="page-head">
        <h1>Tableau de bord -- agents de recette</h1>
        <PageHelp topic="dashboard" />
        <button
          type="button"
          className="dash-reset"
          onClick={() => void resetAll()}
          title="Effacer les runs termines et les traces proxy (l'audit immuable n'est pas touche)"
        >
          Reset tout
        </button>
      </div>

      {error !== null && (
        <div className="dash-error" role="alert">
          {error}
        </div>
      )}

      {notice !== null && (
        <div className="dash-notice" role="status">
          {notice}
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
          <span className="dash-num dash-num-ok" data-testid="kpi-succeeded">
            {tally.succeeded}
          </span>
          <span className="dash-label">launches reussis</span>
        </div>
        <div className="dash-card">
          <span className="dash-num dash-num-fail" data-testid="kpi-failed">
            {tally.failed}
          </span>
          <span className="dash-label">launches rates</span>
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
                    {(() => {
                      const v = voyantFor(status);
                      return (
                        <span className={`voyant ${v.cls}`}>
                          <span className="voyant-dot" />
                          {v.label}
                        </span>
                      );
                    })()}
                  </td>
                  <td>
                    <div className="dash-actions">
                      <button
                        type="button"
                        className="dash-eye"
                        title={
                          runId !== null
                            ? "Voir le run de l'agent"
                            : "Aucun run -- lance l'agent d'abord"
                        }
                        aria-label={`Voir le run de ${agent.id}`}
                        disabled={runId === null}
                        onClick={() =>
                          setViewing({ agentId: agent.id, runId, status })
                        }
                      >
                        <EyeIcon />
                      </button>
                      {active && runId !== null ? (
                        <button
                          type="button"
                          className="dash-stop"
                          onClick={() => void stop(runId)}
                        >
                          Arreter
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn-primary"
                          disabled={launching.has(agent.id)}
                          onClick={() => void launch(agent)}
                        >
                          {launching.has(agent.id) ? "Lancement..." : "Lancer"}
                        </button>
                      )}
                      <button
                        type="button"
                        className="dash-precise"
                        aria-label={`Lancer precis pour ${agent.id}`}
                        title="Composer une instance precise (actions + ressources + profil) et juger le run"
                        onClick={() => setPrecise(agent)}
                      >
                        Lancer precis
                      </button>
                      <button
                        type="button"
                        className="dash-precise"
                        aria-label={`Expliquer ${agent.id}`}
                        title="Voir la fiche de l'agent (identite, capacites, scenario, recette)"
                        onClick={() => setExplaining(agent)}
                      >
                        Expliquer
                      </button>
                    </div>
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

      <div className="page-head dash-camp-head">
        <h2>Campagnes</h2>
      </div>
      <table className="dash-table" aria-label="campagnes">
        <thead>
          <tr>
            <th>Campagne</th>
            <th>Agents (etapes)</th>
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.length === 0 ? (
            <tr>
              <td colSpan={4} className="dash-empty">
                Aucune campagne. Cree-en une dans l'onglet Campagnes.
              </td>
            </tr>
          ) : (
            campaigns.map((c) => {
              const status = campaignStatus(c.id);
              const active = ACTIVE.has(status);
              const v = voyantFor(status);
              return (
                <tr key={c.id}>
                  <td className="dash-agent">
                    <strong>{c.id}</strong>
                    <div className="dash-goal">{c.description}</div>
                  </td>
                  <td>{c.steps.map((s) => s.agent_id).join(", ")}</td>
                  <td>
                    <span className={`voyant ${v.cls}`}>
                      <span className="voyant-dot" />
                      {v.label}
                    </span>
                  </td>
                  <td>
                    <div className="dash-actions">
                      <button
                        type="button"
                        className="dash-eye"
                        title={
                          campaignRun(c.id)
                            ? "Voir le run de la campagne (par etape / agent)"
                            : "Aucun run -- lance la campagne d'abord"
                        }
                        aria-label={`Voir le run de ${c.id}`}
                        disabled={campaignRun(c.id) === undefined}
                        onClick={() => {
                          const r = campaignRun(c.id);
                          if (r !== undefined) {
                            setCampaignViewing({
                              campaign: c,
                              runId: r.id,
                              status: r.status,
                            });
                          }
                        }}
                      >
                        <EyeIcon />
                      </button>
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={active || launchingCampaign.has(c.id)}
                        aria-label={`Lancer la campagne ${c.id}`}
                        onClick={() => void launchCampaign(c)}
                      >
                        {launchingCampaign.has(c.id) ? "Lancement..." : "Lancer"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      <AgentRunModal
        open={viewing !== null}
        agentId={viewing?.agentId ?? ""}
        runId={viewing?.runId ?? null}
        status={viewing?.status ?? ""}
        runs={runs}
        onPurge={async (id) => {
          await purgeRuns(id);
          await poll();
        }}
        onClose={() => setViewing(null)}
      />

      {campaignViewing !== null && (
        <AgentRunModal
          open
          agentId=""
          campaignId={campaignViewing.campaign.id}
          steps={campaignViewing.campaign.steps}
          runId={campaignViewing.runId}
          status={campaignViewing.status}
          runs={runs}
          onClose={() => setCampaignViewing(null)}
        />
      )}

      <PreciseLaunchModal
        open={precise !== null}
        agent={precise}
        onClose={() => {
          setPrecise(null);
          void poll();
        }}
      />

      <AgentExplainModal
        open={explaining !== null}
        agent={explaining}
        onClose={() => setExplaining(null)}
      />
    </div>
  );
}
