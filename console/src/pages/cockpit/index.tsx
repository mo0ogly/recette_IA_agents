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

import {
  Component,
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ErrorInfo, ReactNode } from "react";
import {
  ApiError,
  getProxyTraces,
  launchLaneB,
  listAgents,
  listAiBackends,
  openRunSocket,
  stopRun,
} from "../../api/client";
import type { AgentConfig, AiBackend, ProxyTrace } from "../../types/platform";
import { formatBackend } from "../../lib/aiBackend";
import PageHelp from "../../components/help/PageHelp";
import { LogConsole } from "../../components/LogConsole";
import type { LogLine } from "../../components/LogConsole";
import { distinctValues, filterTraces, traceToLine } from "../proxy/proxyTraceModel";
import "./cockpit.css";

// The project-standard JSON viewer (Monaco), lazy so the editor chunk stays out
// of the base bundle -- same component and pattern as the /proxy page.
const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));

/** Local boundary: a Monaco load failure degrades to a message, not a crash. */
class MonacoBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error): { error: Error } {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Render-path failure already captured in state; nothing else to do.
  }

  render(): ReactNode {
    if (this.state.error !== null) {
      return <div className="cockpit-viewer-msg">editor failed to load: {this.state.error.message}</div>;
    }
    return this.props.children;
  }
}

type Mode = "mock" | "real";

/**
 * Default scripted decisions for a mock run, derived from the SELECTED agent so
 * the run is valid for its target system. A hardcoded `read_repo` only works
 * against the github lab domain; firing it at an okta/finance agent makes the
 * lab return HTTP 404 and the run fails. We therefore script the agent's own
 * first declared capability (always handled by its target domain). An agent
 * with an empty capability_scope (a probe) performs no tool call at all, so it
 * cannot 404. The operator can still edit the script.
 */
function defaultStubScriptFor(agent: AgentConfig | null): string {
  const action = agent?.capability_scope?.[0];
  const steps: Array<Record<string, unknown>> = action
    ? [
        { kind: "tool_call", tool_name: action, tool_args: { resource: "acme/x" } },
        { kind: "final", text: "done" },
      ]
    : [{ kind: "final", text: "probe agent: no capability in scope, nothing to execute" }];
  return JSON.stringify(steps, null, 2);
}

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
    case "tool_call": {
      // WS-B: granular interaction line -- the tool the agent invoked and the
      // arguments it chose. The request/response exchange is in the network log
      // (correlated by event_id).
      const args = (frame.data.args as Record<string, unknown> | undefined) ?? {};
      const keys = Object.keys(args);
      const summary = keys.length ? ` (${keys.map((k) => `${k}=${String(args[k])}`).join(", ")})` : "";
      return `tool_call #${String(frame.data.index ?? "")}: ${String(frame.data.name ?? "")}${summary}`;
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
  const [stubScript, setStubScript] = useState(() => defaultStubScriptFor(null));
  const [error, setError] = useState<string | null>(null);

  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string>("");
  const [frames, setFrames] = useState<LiveFrame[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  // Network log: the side-effect proxy traces (I5) for the active run, so this
  // debug view shows what the agent actually sent to its target system. lane_b
  // runs go through the proxy (the governed audit log never sees them, which is
  // why this replaced the platform-audit tail). Gated by INSPECT_IA_AGENTS_PROXY_DEBUG.
  const [traces, setTraces] = useState<ProxyTrace[]>([]);
  const [proxyDebug, setProxyDebug] = useState<boolean | null>(null);
  const [selectedTraceSeq, setSelectedTraceSeq] = useState<number | null>(null);
  // Which side of the exchange to show: request (agent), response (server), both.
  const [exchangeView, setExchangeView] = useState<"all" | "request" | "response">("all");
  // Network-log filters (empty = "Tous"). Within one run these usually have a
  // single value each, but they let the operator narrow a multi-action run.
  const [filterAgent, setFilterAgent] = useState("");
  const [filterServer, setFilterServer] = useState("");

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
  // Effective pacing delay of the selected/running agent (legibility-first):
  // the operator should see at a glance that an agent is deliberately slowed.
  // The servers list is not in scope in the cockpit, so this resolves to the
  // agent's own pace_ms (the server-inherited pace_ms ?? server.pace_ms ?? 0
  // resolution lives where the servers list is available); 0 means no pacing.
  const effectivePaceMs = selected?.pace_ms ?? 0;

  // Re-derive the default mock script whenever the operator switches agent, so
  // the scripted action always matches the selected agent's target domain.
  useEffect(() => {
    const a = agents.find((x) => x.id === selectedId) ?? null;
    setStubScript(defaultStubScriptFor(a));
  }, [selectedId, agents]);

  // Poll the proxy network log for the active run; no run -> nothing to show.
  useEffect(() => {
    if (runId === null) {
      setTraces([]);
      return;
    }
    let cancelled = false;
    const poll = async (): Promise<void> => {
      try {
        const res = await getProxyTraces(200, runId);
        if (!cancelled) {
          setTraces(res.traces);
          setProxyDebug(res.debug_enabled);
        }
      } catch {
        // Transient poll failure: keep the last view rather than blanking it.
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runId]);

  // A new run clears the filters so a stale agent/server choice does not hide
  // the new run's traces.
  useEffect(() => {
    setFilterAgent("");
    setFilterServer("");
  }, [runId]);

  // Distinct agents/servers present in the run's traces drive the selects.
  const agentOptions = distinctValues(traces, "agent_id");
  const serverOptions = distinctValues(traces, "target_system");
  const visibleTraces = useMemo(
    () =>
      filterTraces(traces, {
        agentId: filterAgent || undefined,
        targetSystem: filterServer || undefined,
      }),
    [traces, filterAgent, filterServer],
  );

  // Auto-select the most recent VISIBLE trace so the exchange (request + server
  // response) is shown immediately, without the operator having to discover the
  // click. A still-visible manual selection is kept.
  useEffect(() => {
    if (visibleTraces.length === 0) {
      setSelectedTraceSeq(null);
      return;
    }
    setSelectedTraceSeq((cur) =>
      cur !== null && visibleTraces.some((t) => t.seq === cur)
        ? cur
        : visibleTraces[visibleTraces.length - 1].seq,
    );
  }, [visibleTraces]);

  const traceLines: LogLine[] = visibleTraces.map((t) => ({
    seq: t.seq,
    level: t.ok ? "info" : "error",
    source: t.agent_id,
    text: `${traceToLine(t).label}${t.error !== null ? ` -- ${t.error}` : ""}`,
  }));
  const selectedTrace = visibleTraces.find((t) => t.seq === selectedTraceSeq) ?? null;

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
                  Backends : {backends.map(formatBackend).join(", ")}
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
            {effectivePaceMs > 0 && (
              <span className="cockpit-pace-badge" title="Cadence imposee a l'agent (pace_ms)">
                pace {effectivePaceMs}ms
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
        {proxyDebug === false && (
          <p className="cockpit-hint" role="status">
            Logs reseau indisponibles : definir INSPECT_IA_AGENTS_PROXY_DEBUG=on cote
            serveur (R5) puis relancer la plateforme.
          </p>
        )}
        <div className="cockpit-log-filters">
          <label>
            <span>Agent</span>
            <select value={filterAgent} onChange={(e) => setFilterAgent(e.target.value)}>
              <option value="">Tous</option>
              {agentOptions.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Serveur</span>
            <select value={filterServer} onChange={(e) => setFilterServer(e.target.value)}>
              <option value="">Tous</option>
              {serverOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>
        <LogConsole
          title={
            runId === null
              ? "Logs reseau (lance l'agent pour tracer ses appels)"
              : `Logs reseau -- run ${runId}`
          }
          lines={traceLines}
          onLineClick={setSelectedTraceSeq}
          selectedSeq={selectedTraceSeq}
        />
        {selectedTrace !== null && (
          <div className="cockpit-exchange" data-testid="cockpit-exchange">
            <div className="cockpit-exchange-meta">
              <strong>
                {selectedTrace.action_type} {selectedTrace.target_system}/
                {selectedTrace.resource}
              </strong>
              <span>{selectedTrace.ok ? "OK" : "FAIL"} {selectedTrace.status_code}</span>
              <span>{selectedTrace.timestamp}</span>
              {selectedTrace.side_effect_hash !== null && (
                <span title={selectedTrace.side_effect_hash}>
                  hash {selectedTrace.side_effect_hash.slice(0, 12)}
                </span>
              )}
            </div>
            {selectedTrace.error !== null && (
              <p className="cockpit-exchange-error" role="alert">
                {selectedTrace.error}
              </p>
            )}
            <div className="cockpit-exchange-head">
              <h4>Echange agent &lt;-&gt; serveur</h4>
              <label className="cockpit-exchange-view">
                <span>Afficher</span>
                <select
                  value={exchangeView}
                  onChange={(e) =>
                    setExchangeView(e.target.value as "all" | "request" | "response")
                  }
                >
                  <option value="all">Tous (requete + reponse)</option>
                  <option value="request">Depart agent (requete)</option>
                  <option value="response">Reponse serveur</option>
                </select>
              </label>
            </div>
            <div className="cockpit-exchange-viewer">
              <MonacoBoundary>
                <Suspense fallback={<div className="cockpit-viewer-msg">chargement de l'editeur...</div>}>
                  <MonacoJsonViewer
                    height="300px"
                    value={JSON.stringify(
                      ((): unknown => {
                        // What the agent actually asks the server: the action and
                        // the target resource (the meaningful intent), plus any
                        // extra payload params. request_payload alone is usually
                        // empty because the args go into action_type + resource.
                        const request = {
                          action_type: selectedTrace.action_type,
                          target_system: selectedTrace.target_system,
                          resource: selectedTrace.resource,
                          payload: selectedTrace.request_payload,
                        };
                        if (exchangeView === "request") return { request };
                        if (exchangeView === "response") return { response: selectedTrace.response };
                        return { request, response: selectedTrace.response };
                      })(),
                      null,
                      2,
                    )}
                  />
                </Suspense>
              </MonacoBoundary>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
