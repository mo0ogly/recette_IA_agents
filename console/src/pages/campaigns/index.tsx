/**
 * Campaigns page -- persisted, on-demand discovery-recette campaigns.
 *
 * A campaign is an ordered set of agent launches. Each agent already carries
 * its own actions (its scenario, composed from the action catalog on the
 * Agents tab); a campaign just selects which agents run, in order. Running one
 * streams live frames into the run console and persists one recording per step;
 * a recording can be replayed deterministically (I4).
 *
 * Status per campaign is polled from GET /runs (matched on campaign_id).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createCampaign,
  deleteCampaign,
  instantiateTemplate,
  listAgents,
  listCampaigns,
  listCampaignTemplates,
  listRecordings,
  listRuns,
  replayRecording,
  runCampaign,
} from "../../api/client";
import { useRunStream } from "../../hooks/useRunStream";
import type { RunFrame } from "../../hooks/useRunStream";
import type {
  AgentConfig,
  Campaign,
  CampaignTemplate,
  RecordingMeta,
  RunSummary,
} from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import { LogConsole } from "../../components/LogConsole";
import type { LogLine } from "../../components/LogConsole";
import "./campaigns.css";

const POLL_MS = 2000;
const ACTIVE = new Set(["pending", "running"]);

function frameLine(f: RunFrame): string {
  const d = f.data;
  const agent = d.agent_id ? ` ${String(d.agent_id)}` : "";
  switch (f.type) {
    case "start":
      return "run start";
    case "agent_start":
      return `agent_start${agent} (${String(d.provider ?? "")})`;
    case "step":
      return `step${agent} #${String(d.index ?? "")}`;
    case "agent_done":
      return `agent_done${agent} -> ${String(d.actions ?? 0)} actions, rec=${String(d.recording_id ?? "")}`;
    case "campaign_done":
      return `campaign_done (${String(d.steps ?? 0)} steps)`;
    case "step_error":
      return `step_error${agent}: ${String(d.message ?? "")}`;
    case "replay_result":
      return `replay_result: matches_original=${String(d.matches_original)}`;
    case "error":
      return `error: ${String(d.message ?? "")}`;
    case "end":
      return `end (${String(d.status ?? "")})`;
    default:
      return f.type;
  }
}

/** Map one streamed campaign frame to a displayable log line.
 *  Step failures (step_error) and run failures (error) are error-level. */
function frameToLogLine(f: RunFrame): LogLine {
  return {
    seq: f.seq,
    level: f.type === "step_error" || f.type === "error" ? "error" : "info",
    source: typeof f.data.agent_id === "string" ? f.data.agent_id : "run",
    text: frameLine(f),
  };
}

export default function CampaignsPage(): JSX.Element {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [recordings, setRecordings] = useState<RecordingMeta[]>([]);
  const [templates, setTemplates] = useState<CampaignTemplate[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [newId, setNewId] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const stream = useRunStream();
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [c, a, r, t] = await Promise.all([
        listCampaigns(),
        listAgents(),
        listRecordings(),
        listCampaignTemplates(),
      ]);
      setCampaigns(c);
      setAgents(a);
      setRecordings(r);
      setTemplates(t);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      setRuns(await listRuns());
    } catch {
      // transient
    }
  }, []);

  useEffect(() => {
    void refresh();
    void poll();
    timer.current = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      if (timer.current !== null) {
        window.clearInterval(timer.current);
      }
    };
  }, [refresh, poll]);

  const statusOf = (campaignId: string): string => {
    const latest = runs.find((r) => r.campaign_id === campaignId);
    return latest?.status ?? "";
  };

  const togglePick = (id: string): void => {
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const create = useCallback(async () => {
    const id = newId.trim();
    if (id === "" || picked.length === 0) {
      setError("Donne un id de campagne et coche au moins un agent.");
      return;
    }
    try {
      await createCampaign({
        id,
        description: newDesc.trim(),
        steps: picked.map((agentId) => ({ agent_id: agentId })),
      });
      setNewId("");
      setNewDesc("");
      setPicked([]);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [newId, newDesc, picked, refresh]);

  const instantiate = useCallback(
    async (id: string) => {
      try {
        await instantiateTemplate(id);
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      if (!window.confirm(`Supprimer la campagne "${id}" ?`)) {
        return;
      }
      try {
        await deleteCampaign(id);
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refresh],
  );

  const run = useCallback(
    async (id: string) => {
      await stream.start(() => runCampaign(id));
      window.setTimeout(() => void Promise.all([refresh(), poll()]), 1500);
    },
    [stream, refresh, poll],
  );

  const replay = useCallback(
    async (recordingId: string) => {
      await stream.start(() => replayRecording(recordingId));
    },
    [stream],
  );

  const replayResult = stream.frames.find((f) => f.type === "replay_result");

  return (
    <div>
      <div className="page-head">
        <h1>Campagnes</h1>
        <PageHelp topic="campaigns" />
      </div>

      {error !== null && (
        <div className="camp-error" role="alert">
          {error}
        </div>
      )}

      <section className="panel camp-templates">
        <h2>Modeles de campagnes (par agent et usage)</h2>
        <p className="camp-desc">
          Un clic instancie l'agent mock et la campagne prets a lancer. Profil :
          legit (autorise), suspect (depassement), destructif (irreversible).
        </p>
        <table className="camp-table">
          <thead>
            <tr>
              <th>Campagne</th>
              <th>Systeme</th>
              <th>Profil</th>
              <th>Actions</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => {
              const exists = campaigns.some((c) => c.id === t.id);
              return (
                <tr key={t.id}>
                  <td>
                    <strong>{t.title}</strong>
                    <div className="camp-mono camp-desc">{t.id}</div>
                  </td>
                  <td className="camp-mono">{t.target_system}</td>
                  <td>
                    <span className={`pill pill-profile-${t.profile}`}>{t.profile}</span>
                  </td>
                  <td className="camp-mono">{t.actions.join(", ")}</td>
                  <td>
                    <button
                      type="button"
                      onClick={() => void instantiate(t.id)}
                      disabled={exists}
                    >
                      {exists ? "Instancie" : "Instancier"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <div className="camp-grid">
        <section className="panel">
          <h2>Campagnes</h2>
          {campaigns.length === 0 ? (
            <p className="camp-empty">Aucune campagne. Cree-en une a droite.</p>
          ) : (
            <table className="camp-table">
              <thead>
                <tr>
                  <th>Id</th>
                  <th>Agents (etapes)</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => {
                  const st = statusOf(c.id);
                  const active = ACTIVE.has(st);
                  return (
                    <tr key={c.id}>
                      <td>
                        <strong>{c.id}</strong>
                        <div className="camp-desc">{c.description}</div>
                      </td>
                      <td className="camp-mono">
                        {c.steps.map((s) => s.agent_id).join(", ")}
                      </td>
                      <td>
                        <span className={`dot dot-${active ? "on" : "off"}`} />
                        {active ? "actif" : st === "" ? "jamais lance" : st}
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => void run(c.id)}
                          disabled={active}
                        >
                          Lancer
                        </button>
                        <button
                          type="button"
                          className="camp-danger"
                          onClick={() => void remove(c.id)}
                        >
                          Suppr
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <h2 className="camp-h2-spaced">Enregistrements (replay I4)</h2>
          {recordings.length === 0 ? (
            <p className="camp-empty">Aucun enregistrement. Lance une campagne.</p>
          ) : (
            <table className="camp-table">
              <thead>
                <tr>
                  <th>Recording</th>
                  <th>Agent</th>
                  <th>Etapes</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {recordings.map((r) => (
                  <tr key={r.recording_id}>
                    <td className="camp-mono">{r.recording_id}</td>
                    <td>{r.agent_id}</td>
                    <td>{r.steps}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => void replay(r.recording_id)}
                        disabled={stream.running}
                      >
                        Replay
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel">
          <h2>Nouvelle campagne</h2>
          <label className="camp-field">
            <span>Id</span>
            <input value={newId} onChange={(e) => setNewId(e.target.value)} />
          </label>
          <label className="camp-field">
            <span>Description</span>
            <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
          </label>
          <fieldset className="camp-agents">
            <legend>Agents (etapes, dans l'ordre) -- leurs actions viennent de l'onglet Agents</legend>
            {agents.length === 0 && <p className="camp-empty">Aucun agent configure.</p>}
            {agents.map((a) => (
              <label key={a.id} className="camp-agent-row">
                <input
                  type="checkbox"
                  checked={picked.includes(a.id)}
                  onChange={() => togglePick(a.id)}
                />
                {a.id} ({a.target_system ?? "?"}) --{" "}
                {(a.capability_scope ?? []).join(", ") || "aucune action"}
              </label>
            ))}
          </fieldset>
          <button type="button" onClick={() => void create()}>
            Creer la campagne
          </button>

          <div className="camp-h2-spaced">
            {stream.runId !== null && (
              <p className="camp-status">
                run {stream.runId} -- {stream.status}
              </p>
            )}
            {replayResult && (
              <p className="camp-replay">
                Replay determinisme :{" "}
                <span
                  className={`pill ${replayResult.data.matches_original ? "pill-ok" : "pill-bad"}`}
                >
                  {replayResult.data.matches_original ? "IDENTIQUE" : "DIVERGENT"}
                </span>
              </p>
            )}
            <LogConsole
              title="Console du run"
              lines={stream.frames.map(frameToLogLine)}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
