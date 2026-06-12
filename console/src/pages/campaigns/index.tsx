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
  listAgents,
  listCampaigns,
  listRecordings,
  listRuns,
  replayRecording,
  runCampaign,
} from "../../api/client";
import { useRunStream } from "../../hooks/useRunStream";
import type {
  AgentConfig,
  Campaign,
  RecordingMeta,
  RunSummary,
} from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import "./campaigns.css";

const POLL_MS = 2000;
const ACTIVE = new Set(["pending", "running"]);

function frameLine(f: { seq: number; type: string; data: Record<string, unknown> }): string {
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

export default function CampaignsPage(): JSX.Element {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [recordings, setRecordings] = useState<RecordingMeta[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [newId, setNewId] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const stream = useRunStream();
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [c, a, r] = await Promise.all([
        listCampaigns(),
        listAgents(),
        listRecordings(),
      ]);
      setCampaigns(c);
      setAgents(a);
      setRecordings(r);
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

          <h2 className="camp-h2-spaced">Console du run</h2>
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
          <div className="camp-console">
            {stream.frames.length === 0 ? (
              <span className="camp-console-empty">
                Lance une campagne ou un replay pour voir le flux ici.
              </span>
            ) : (
              stream.frames.map((f) => (
                <div key={f.seq} className={`camp-cline camp-${f.type}`}>
                  <span className="camp-cseq">{String(f.seq).padStart(2, "0")}</span>
                  {frameLine(f)}
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
