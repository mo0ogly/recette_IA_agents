/**
 * Cockpit page -- the heart of the discovery recette platform.
 *
 * This is NOT the discovery tool: it is the bench that produces the test
 * subjects the discovery tool must detect. The operator picks a configured
 * agent, chooses whether it runs as a mock (scripted stub) or behind a real
 * AI (its bound ai_backend, key from env), launches it, watches the live
 * action stream, and stops it. Launches go through POST /runs (kind=lane_b)
 * and the live frames arrive over the run WebSocket.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  launchLaneB,
  listAgents,
  listAiBackends,
  openRunSocket,
  stopRun,
} from "../../api/client";
import type { AgentConfig, AiBackend } from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import { auditEventToLogLine, LogConsole } from "../../components/LogConsole";
import { useAuditTail } from "../../hooks/useAuditTail";
import "./cockpit.css";

type Mode = "mock" | "real";

/** Default scripted decisions for a mock run; the operator can edit them. */
const DEFAULT_STUB_SCRIPT = JSON.stringify(
  [
    { kind: "tool_call", tool_name: "read_repo", tool_args: { resource: "acme/x" } },
    { kind: "final", text: "done" },
  ],
  null,
  2,
);

interface LiveFrame {
  seq: number;
  type: string;
  data: Record<string, unknown>;
}

function frameLine(frame: LiveFrame): string {
  switch (frame.type) {
    case "start":
      return `start (kind=${String(frame.data.kind ?? "")})`;
    case "step": {
      const action = frame.data.action as Record<string, unknown> | undefined;
      const at = action ? `${action.action_type}@${action.target_system}` : "(no action)";
      return `step #${String(frame.data.index ?? "")}: ${at}`;
    }
    case "result": {
      const actions = (frame.data.actions as unknown[] | undefined) ?? [];
      return `result: ${actions.length} action(s) recorded`;
    }
    case "error":
      return `error: ${String(frame.data.message ?? "")}`;
    case "end":
      return `end (status=${String(frame.data.status ?? "")})`;
    default:
      return frame.type;
  }
}

export default function CockpitPage(): JSX.Element {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [backends, setBackends] = useState<AiBackend[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [mode, setMode] = useState<Mode>("mock");
  const [stubScript, setStubScript] = useState(DEFAULT_STUB_SCRIPT);
  const [error, setError] = useState<string | null>(null);

  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string>("");
  const [frames, setFrames] = useState<LiveFrame[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  // Unfiltered tail of the platform audit log while the page is mounted (I1).
  const audit = useAuditTail();

  const loadConfig = useCallback(async () => {
    setError(null);
    try {
      const [a, b] = await Promise.all([listAgents(), listAiBackends()]);
      setAgents(a);
      setBackends(b);
      if (a.length > 0 && selectedId === "") {
        setSelectedId(a[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [selectedId]);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  // Tear the socket down when the component unmounts.
  useEffect(() => {
    return () => socketRef.current?.close();
  }, []);

  const selected = agents.find((a) => a.id === selectedId) ?? null;
  const running = runStatus === "running" || runStatus === "pending";

  const launch = useCallback(async () => {
    if (selectedId === "") {
      return;
    }
    setError(null);
    setFrames([]);
    let stub: Array<Record<string, unknown>> | undefined;
    if (mode === "mock") {
      try {
        stub = JSON.parse(stubScript) as Array<Record<string, unknown>>;
      } catch {
        setError("Le script mock n'est pas un JSON valide.");
        return;
      }
    }
    try {
      const handle = await launchLaneB({ agent_id: selectedId, stub_script: stub });
      setRunId(handle.run_id);
      setRunStatus(handle.status);
      const socket = openRunSocket(handle.run_id);
      socketRef.current = socket;
      socket.onmessage = (ev) => {
        const frame = JSON.parse(ev.data as string) as LiveFrame;
        setFrames((prev) => [...prev, frame]);
        if (frame.type === "end") {
          setRunStatus(String(frame.data.status ?? "done"));
          socket.close();
        }
      };
      socket.onopen = () => setRunStatus("running");
      socket.onerror = () => setError("WebSocket: flux interrompu.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Lancement refuse (${err.status}): ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }, [selectedId, mode, stubScript]);

  const stop = useCallback(async () => {
    if (runId === null) {
      return;
    }
    try {
      await stopRun(runId);
      setRunStatus("stopped");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [runId]);

  const realDisabled = mode === "real" && (!selected || !selected.ai_backend_id);

  return (
    <div>
      <div className="page-head">
        <h1>Cockpit -- lancer les agents de test</h1>
        <PageHelp topic="cockpit" />
      </div>

      {error !== null && (
        <div className="cockpit-error" role="alert">
          {error}
        </div>
      )}

      <div className="cockpit-grid">
        <section className="panel cockpit-launch">
          <h2>Lancement</h2>

          <label className="cockpit-field">
            <span>Agent</span>
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              disabled={running}
            >
              {agents.length === 0 && <option value="">(aucun agent configure)</option>}
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.id} -- {a.target_system ?? "?"} / {a.goal ?? "(sans but)"}
                </option>
              ))}
            </select>
          </label>

          <fieldset className="cockpit-mode" disabled={running}>
            <legend>Type d'agent</legend>
            <label>
              <input
                type="radio"
                name="mode"
                checked={mode === "mock"}
                onChange={() => setMode("mock")}
              />
              Mock (script deterministe, zero cle)
            </label>
            <label>
              <input
                type="radio"
                name="mode"
                checked={mode === "real"}
                onChange={() => setMode("real")}
              />
              IA reelle (ai_backend, cle en env)
            </label>
          </fieldset>

          {mode === "real" && (
            <p className="cockpit-hint">
              {selected?.ai_backend_id
                ? `IA derriere : ${selected.ai_backend_id}`
                : "Cet agent n'a pas d'ai_backend. Liez-en un dans l'onglet Agents."}
              {backends.length > 0 && (
                <>
                  {" "}
                  Backends : {backends.map((b) => `${b.id} (${b.provider}/${b.model})`).join(", ")}
                </>
              )}
            </p>
          )}

          {mode === "mock" && (
            <label className="cockpit-field">
              <span>Script mock (decisions JSON)</span>
              <textarea
                className="cockpit-script"
                value={stubScript}
                onChange={(e) => setStubScript(e.target.value)}
                rows={8}
                disabled={running}
              />
            </label>
          )}

          <div className="cockpit-actions">
            <button
              type="button"
              onClick={() => void launch()}
              disabled={running || selectedId === "" || realDisabled}
            >
              Lancer
            </button>
            <button
              type="button"
              className="cockpit-stop"
              onClick={() => void stop()}
              disabled={!running}
            >
              Arreter
            </button>
          </div>
        </section>

        <section className="panel cockpit-live">
          <h2>
            Flux live{" "}
            {runId !== null && (
              <span className="cockpit-run-id">
                {runId} -- {runStatus}
              </span>
            )}
          </h2>
          {frames.length === 0 ? (
            <p className="cockpit-empty">Aucun run en cours. Lancez un agent.</p>
          ) : (
            <ol className="cockpit-frames">
              {frames.map((f) => (
                <li key={f.seq} className={`frame frame-${f.type}`}>
                  <span className="frame-seq">{f.seq}</span>
                  {frameLine(f)}
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <section className="cockpit-audit">
        <LogConsole
          title="Platform audit"
          lines={audit.events.map(auditEventToLogLine)}
          onClear={audit.clear}
        />
      </section>
    </div>
  );
}
