/**
 * Orchestration page (Phase 9) -- drive a multi-agent team live, then follow it
 * on the wire.
 *
 * The console can DRIVE a declared team (POST /orchestrate/run) through real
 * per-instance LLM backends, see the four-dimension verdict + the routed run,
 * and deep-link each acting instance / session straight into the wire packet
 * list (filtered by instance/session). This is what pulls the orchestrator out
 * of the dark: an analyst launches a team and follows one agent across the
 * capture. Read-only after the run; all non-determinism lives in the backends.
 */

import { useEffect, useState, type JSX } from "react";
import { Link } from "react-router-dom";

import {
  listOrchestrationSessions,
  runOrchestration,
  type OrchestrationRunResult,
  type OrchestrationSessionSummary,
} from "../../api/client";
import "./orchestrate.css";

// A minimal, valid handoff team as the editable starting point (the same shape
// the corpus uses). The operator edits it, picks a provider/model, and drives.
const _SAMPLE_TEAM = JSON.stringify(
  {
    kind: "maf_orchestration",
    agent_id: "drive-handoff",
    name: "Drive Handoff",
    start_agent: "triage",
    termination: { max_hops: 8 },
    participants: [
      {
        agent_id: "triage",
        declared_identity: { provider: "AzureOpenAI", model: "m" },
        handoffs: [{ target: "worker" }],
      },
      {
        agent_id: "worker",
        declared_identity: { provider: "AzureOpenAI", model: "m" },
        handoffs: [{ target: "triage" }],
        tools: [{ tool_kind: "mcp", target: "mcp://x", approval: "always" }],
      },
    ],
  },
  null,
  2,
);

/** Deep-link into the wire packet list filtered to one instance / session. */
function wireLink(params: { instance?: string; session?: string }): string {
  const q = new URLSearchParams({ source: "wire" });
  if (params.instance) q.set("instance", params.instance);
  if (params.session) q.set("session", params.session);
  return `/proxy?${q.toString()}`;
}

export default function OrchestratePage(): JSX.Element {
  const [teamJson, setTeamJson] = useState(_SAMPLE_TEAM);
  const [provider, setProvider] = useState("groq");
  const [model, setModel] = useState("llama-3.3-70b-versatile");
  const [sessionId, setSessionId] = useState("sess-1");
  const [result, setResult] = useState<OrchestrationRunResult | null>(null);
  const [sessions, setSessions] = useState<OrchestrationSessionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshSessions = (): void => {
    listOrchestrationSessions()
      .then((r) => setSessions(r.sessions))
      .catch(() => setSessions([]));
  };
  useEffect(refreshSessions, []);

  const onRun = (): void => {
    setError(null);
    let team: Record<string, unknown>;
    try {
      team = JSON.parse(teamJson) as Record<string, unknown>;
    } catch {
      setError("team JSON invalide");
      return;
    }
    setBusy(true);
    runOrchestration({ team, providers: { provider, model }, session_id: sessionId })
      .then((r) => {
        setResult(r);
        refreshSessions();
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  return (
    <section className="orch-page" data-testid="orchestrate-page">
      <header className="orch-head">
        <h1>Orchestration</h1>
        <p className="orch-sub">
          Piloter une equipe multi-agents en direct, puis suivre chaque instance sur le
          reseau (wire).
        </p>
      </header>

      <div className="orch-grid">
        <div className="orch-form">
          <label className="orch-label">
            Equipe (team.json)
            <textarea
              className="orch-textarea"
              data-testid="orchestrate-team"
              rows={16}
              value={teamJson}
              onChange={(e) => setTeamJson(e.target.value)}
              spellCheck={false}
            />
          </label>
          <div className="orch-row">
            <label className="orch-label">
              provider
              <input
                className="orch-input"
                data-testid="orchestrate-provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              />
            </label>
            <label className="orch-label">
              model
              <input
                className="orch-input"
                data-testid="orchestrate-model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
            </label>
            <label className="orch-label">
              session_id
              <input
                className="orch-input"
                data-testid="orchestrate-session"
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
              />
            </label>
          </div>
          <button
            type="button"
            className="orch-run"
            data-testid="orchestrate-run"
            disabled={busy}
            onClick={onRun}
          >
            {busy ? "Execution..." : "Lancer l'orchestration"}
          </button>
          {error !== null && (
            <p className="orch-error" role="alert" data-testid="orchestrate-error">
              {error}
            </p>
          )}
        </div>

        <div className="orch-result">
          {result === null ? (
            <p className="orch-empty">
              Editer l'equipe et lancer : le verdict et le run apparaissent ici, chaque
              instance deep-linke vers ses flux reseau.
            </p>
          ) : (
            <div data-testid="orchestrate-verdict">
              <div className="orch-verdict" data-verdict={result.verdict}>
                verdict : <strong>{result.verdict}</strong>
                <span className="orch-dims">
                  {Object.entries(result.dimensions).map(([k, ok]) => (
                    <span key={k} className="orch-dim" data-ok={ok} title={k}>
                      {k.replace(/_/g, " ")}
                    </span>
                  ))}
                </span>
              </div>

              <div className="orch-instances">
                <span className="orch-muted">instances :</span>
                {result.instances.map((iid) => (
                  <Link
                    key={iid}
                    className="orch-chip"
                    data-testid={`orchestrate-instance-${iid}`}
                    to={wireLink({ instance: iid, session: result.session_id })}
                  >
                    {iid} {"->"} flux wire
                  </Link>
                ))}
              </div>

              {result.run.hops.length > 0 && (
                <ol className="orch-hops" data-testid="orchestrate-hops">
                  {result.run.hops.map((h) => (
                    <li key={h.seq}>
                      <code>{h.from}</code> {"->"} <code>{h.to}</code>
                      {h.reason ? <span className="orch-muted"> ({h.reason})</span> : null}
                    </li>
                  ))}
                </ol>
              )}

              {result.run.actions.length > 0 && (
                <table className="orch-actions">
                  <tbody>
                    {result.run.actions.map((a) => (
                      <tr key={a.seq}>
                        <td>
                          <code>{a.agent_id}</code>
                        </td>
                        <td className="orch-muted">
                          {a.tool_kind ?? "-"} {"->"} {a.target}
                        </td>
                        <td>{a.approved ? "approuve" : "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {sessions.length > 0 && (
            <div className="orch-sessions" data-testid="orchestrate-sessions">
              <span className="orch-muted">sessions suivies :</span>
              {sessions.map((s) => (
                <Link
                  key={s.session_id}
                  className="orch-chip"
                  to={wireLink({ session: s.session_id })}
                >
                  {s.session_id} · {s.instances.length} instance(s)
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
