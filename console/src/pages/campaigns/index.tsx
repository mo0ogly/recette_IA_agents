/**
 * Campaigns page -- persisted, on-demand discovery-recette campaigns.
 *
 * A campaign is an ordered set of agent launches the discovery team runs on
 * demand. Running one streams live frames (reused run WebSocket) and persists
 * one recording per step; each recording can then be replayed deterministically
 * (I4) -- the replay reports whether its action log matches the original.
 */

import { useCallback, useEffect, useState } from "react";
import {
  createCampaign,
  deleteCampaign,
  listAgents,
  listCampaigns,
  listRecordings,
  replayRecording,
  runCampaign,
} from "../../api/client";
import { useRunStream } from "../../hooks/useRunStream";
import type { AgentConfig, Campaign, RecordingMeta } from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import "./campaigns.css";

export default function CampaignsPage(): JSX.Element {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [recordings, setRecordings] = useState<RecordingMeta[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Create form: id + description + selected agents (mock by default).
  const [newId, setNewId] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const stream = useRunStream();

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

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const togglePick = (id: string): void => {
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const create = useCallback(async () => {
    const id = newId.trim();
    if (id === "" || picked.length === 0) {
      setError("Campaign id and at least one agent are required.");
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
      if (!window.confirm(`Delete campaign "${id}"?`)) {
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
      // Recordings appear once the run finishes; refresh shortly after.
      window.setTimeout(() => void refresh(), 1500);
    },
    [stream, refresh],
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
                  <th>Description</th>
                  <th>Etapes</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td>{c.description}</td>
                    <td>{c.steps.length}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => void run(c.id)}
                        disabled={stream.running}
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
                ))}
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
            <legend>Agents (etapes, dans l'ordre)</legend>
            {agents.length === 0 && <p className="camp-empty">Aucun agent configure.</p>}
            {agents.map((a) => (
              <label key={a.id} className="camp-agent-row">
                <input
                  type="checkbox"
                  checked={picked.includes(a.id)}
                  onChange={() => togglePick(a.id)}
                />
                {a.id} ({a.target_system ?? "?"})
              </label>
            ))}
          </fieldset>
          <button type="button" onClick={() => void create()}>
            Creer la campagne
          </button>

          <h2 className="camp-h2-spaced">Flux du dernier run</h2>
          {stream.runId !== null && (
            <p className="camp-status">
              {stream.runId} -- {stream.status}
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
          {stream.frames.length === 0 ? (
            <p className="camp-empty">Lance une campagne ou un replay.</p>
          ) : (
            <ol className="camp-frames">
              {stream.frames.map((f) => (
                <li key={f.seq} className={`frame frame-${f.type}`}>
                  <span className="frame-seq">{f.seq}</span>
                  {f.type}
                  {f.data.agent_id ? ` ${String(f.data.agent_id)}` : ""}
                  {f.data.recording_id ? ` -> ${String(f.data.recording_id)}` : ""}
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
