/**
 * AgentRunModal -- "eye" view of an agent, opened from the dashboard / agents
 * eye button. Two tabs:
 *
 *  - Run courant (JSON): the CURRENT run's ordered frames (start / step /
 *    result / end), combining the server snapshot (getRunEvents) with the live
 *    run WebSocket (openRunSocket), de-duplicated by frame seq, in a lazy
 *    Monaco viewer (read-only; the editor chunk stays out of the base bundle).
 *
 *  - Historique des runs: every run launched for this agent (the ephemeral run
 *    read-model), newest first, each with its status light. It grows with every
 *    relaunch. A "Purger" button clears the agent's finished runs -- this only
 *    touches the in-memory run records, NEVER the append-only audit log (I1);
 *    active runs are preserved server-side.
 *
 * Frames accumulate in a ref so React StrictMode's double-invoke never wipes
 * them; the ref resets only when the run changes. Fetchers and the socket
 * factory are injectable so the contract test runs without a live backend.
 */

import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  getProxyTraces,
  getRunEvents,
  getRunVerdict,
  openRunSocket,
  submitRunVerdict,
} from "../api/client";
import ProxySelector from "./ProxySelector";
import type {
  ProxyTrace,
  ProxyTraceResponse,
  RunEvent,
  RunSummary,
  RunVerdict,
  RunVerdictSubmission,
} from "../types/platform";
import { voyantFor } from "../lib/runStatus";
import HelpModal from "./HelpModal";
import { CampaignStepsView, groupSteps } from "./campaignSteps";
import type { CampaignStepRef } from "./campaignSteps";

const MonacoJsonViewer = lazy(() => import("./MonacoJsonViewer"));

export interface AgentRunModalProps {
  open: boolean;
  agentId: string;
  runId: string | null;
  /** Last known run status from the poll (fallback before frames arrive). */
  status: string;
  /** Parent's polled runs; the Journal shows those for this agent. */
  runs?: RunSummary[];
  /** Campaign mode: when set, the modal is the eye of a multi-agent CAMPAIGN
   *  run -- the title, the run history (filtered by campaign_id), and an extra
   *  "Etapes (agents)" tab reflect the campaign instead of a single agent. */
  campaignId?: string;
  /** The campaign's declared steps (campaign mode), shown as the plan before a
   *  run exists and folded per agent once the run streams. */
  steps?: CampaignStepRef[];
  onClose: () => void;
  /** Purge this agent's finished runs (DELETE /runs?agent_id=). */
  onPurge?: (agentId: string) => Promise<void> | void;
  /** Current-run snapshot fetcher; defaults to GET /runs/{id}/events. */
  fetchEvents?: (runId: string) => Promise<RunEvent[]>;
  /** Live run socket factory; defaults to the run WebSocket. */
  socketFactory?: (runId: string) => WebSocket;
  /** Run verdict fetcher (F1); defaults to GET /runs/{id}/verdict. */
  fetchVerdict?: (runId: string) => Promise<RunVerdict>;
  /** Push this run onto the Verdicts board; defaults to POST
   *  /runs/{id}/submit-verdict. Injectable for the contract test. */
  submitVerdict?: (runId: string) => Promise<RunVerdictSubmission>;
  /** Proxy traces fetcher for this run (deep-link); defaults to
   *  GET /proxy/traces?run_id=. */
  fetchTraces?: (runId: string) => Promise<ProxyTraceResponse>;
}

/** A run frame carries a numeric seq once it has been through the run manager. */
function frameSeq(frame: RunEvent): number | null {
  const seq = (frame as { seq?: unknown }).seq;
  return typeof seq === "number" ? seq : null;
}

/** Derive the run lifecycle state from the frames seen so far. */
function deriveState(frames: RunEvent[], fallback: string): string {
  if (frames.some((f) => f.type === "end")) {
    return frames.some((f) => f.type === "error") ? "failed" : "completed";
  }
  if (frames.length > 0) {
    return "running";
  }
  return fallback === "" ? "inactif" : fallback;
}

interface LogLine {
  seq: number | null;
  kind: string;
  text: string;
  tone: "info" | "action" | "ok" | "error";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

/** Translate a run frame into a readable, detailed log line. */
function frameToLine(frame: RunEvent): LogLine {
  const seq = frameSeq(frame);
  const data = asRecord((frame as { data?: unknown }).data);
  switch (frame.type) {
    case "start":
      return { seq, kind: "start", text: `run demarre (${String(data.kind ?? "lane_b")})`, tone: "info" };
    case "step": {
      const action = asRecord(data.action);
      if (Object.keys(action).length === 0) {
        return { seq, kind: "step", text: "etape sans action externe", tone: "info" };
      }
      const target = String(action.target_system ?? "?");
      const type = String(action.action_type ?? "?");
      const resource = action.resource ? ` ${String(action.resource)}` : "";
      const mode = action.mode ? ` [${String(action.mode)}]` : "";
      return { seq, kind: "action", text: `${type} -> ${target}${resource}${mode}`, tone: "action" };
    }
    case "result": {
      const actions = Array.isArray(data.actions) ? data.actions.length : 0;
      return { seq, kind: "result", text: `resultat: ${actions} action(s) executee(s)`, tone: "ok" };
    }
    case "end":
      return { seq, kind: "end", text: "run termine", tone: "ok" };
    case "error":
    case "step_error":
      return { seq, kind: "error", text: `erreur: ${String(data.message ?? frame.type)}`, tone: "error" };
    default:
      return { seq, kind: frame.type, text: frame.type, tone: "info" };
  }
}

interface DecideRow {
  index: number;
  decision: string;
  action: string | null;
}

/** F2: pair each LLM decision with the side effect it produced, from the run's
 *  step frames (which now carry both the decision and the executed action). */
function decideRows(frames: RunEvent[]): DecideRow[] {
  const rows: DecideRow[] = [];
  for (const frame of frames) {
    if (frame.type !== "step") {
      continue;
    }
    const data = asRecord((frame as { data?: unknown }).data);
    const decision = asRecord(data.decision);
    const index = typeof data.index === "number" ? data.index : rows.length;
    let decisionText: string;
    if (decision.kind === "tool_call") {
      const args = asRecord(decision.tool_args);
      const resource = args.resource ? String(args.resource) : "";
      decisionText = `${String(decision.tool_name ?? "?")}(${resource})`;
    } else if (Object.keys(decision).length > 0) {
      decisionText = `final: ${String(decision.text ?? "")}`;
    } else {
      decisionText = "(decision indisponible)";
    }
    const action = asRecord(data.action);
    const actionText =
      Object.keys(action).length > 0
        ? `${String(action.action_type)} -> ${String(action.target_system)}/${String(action.resource)}`
        : null;
    rows.push({ index, decision: decisionText, action: actionText });
  }
  return rows;
}

/** F2 tab body: the decide -> act chain (why each side effect happened). */
function DecideView(props: { runId: string | null; frames: RunEvent[] }): JSX.Element {
  const { runId, frames } = props;
  if (runId === null) {
    return <p className="run-empty">Aucun run courant. Lance l'agent d'abord.</p>;
  }
  const rows = decideRows(frames);
  if (rows.length === 0) {
    return <p className="run-empty">Aucune decision encore (le run n'a pas agi).</p>;
  }
  return (
    <ol className="run-decide" data-testid="run-decide">
      {rows.map((row) => (
        <li key={row.index} className="run-decide-row">
          <span className="run-decide-seq">{row.index}</span>
          <span className="run-decide-decision" title="decision du LLM">
            {row.decision}
          </span>
          <span className="run-decide-arrow">{"->"}</span>
          <span className="run-decide-action" title="effet de bord execute">
            {row.action ?? "(pas d'action externe)"}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Deep-link tab body: the side-effect traces this run produced, filtered to the
 *  run (F3). Shows the debug-off hint when proxy tracing is disabled. */
function RunTracesView(props: {
  runId: string | null;
  loading: boolean;
  error: string | null;
  debugEnabled: boolean;
  traces: ProxyTrace[] | null;
}): JSX.Element {
  const { runId, loading, error, debugEnabled, traces } = props;
  // The proxy-route selector lives at the top of the network log: an operator
  // picks the transport (direct vs wire overlay) for the NEXT run from here,
  // alongside the traces this run produced.
  let inner: JSX.Element;
  if (runId === null) {
    inner = <p className="run-empty">Aucun run courant. Lance l'agent d'abord.</p>;
  } else if (error !== null) {
    inner = <p role="alert">Erreur de chargement des traces : {error}</p>;
  } else if (traces === null) {
    inner = <p className="run-empty">{loading ? "Chargement des traces..." : "Pas de traces."}</p>;
  } else if (traces.length === 0) {
    inner = (
      <p className="run-empty" data-testid="run-traces-empty">
        {debugEnabled
          ? "Aucun effet de bord trace pour ce run (agent en memoire ou sans action externe)."
          : "Tracage proxy desactive (INSPECT_IA_AGENTS_PROXY_DEBUG=on cote serveur pour capter la comm)."}
      </p>
    );
  } else {
    inner = (
      <ol className="run-traces" data-testid="run-traces">
        {traces.map((t) => (
          <li key={t.seq} className={`run-trace-row ${t.ok ? "tone-ok" : "tone-error"}`}>
            <span className="run-trace-seq">{t.seq}</span>
            <span className="run-trace-action mono">
              {t.action_type} {"->"} {t.target_system}/{t.resource}
            </span>
            <span className="run-trace-status">
              {t.ok ? "ok" : "fail"} {t.status_code}
            </span>
          </li>
        ))}
      </ol>
    );
  }
  return (
    <>
      <ProxySelector />
      {inner}
    </>
  );
}

/** F1 verdict tab body: the 4 recette dimensions + typed capability violations
 *  + the global verdict, judged from the run's real action log. */
function RunVerdictView(props: {
  runId: string | null;
  loading: boolean;
  error: string | null;
  verdict: RunVerdict | null;
  onSubmit: () => void;
  submitting: boolean;
  submitResult: RunVerdictSubmission | null;
  submitError: string | null;
}): JSX.Element {
  const { runId, loading, error, verdict, onSubmit, submitting, submitResult, submitError } =
    props;
  if (runId === null) {
    return (
      <p className="run-empty">Aucun run courant a juger. Lance l'agent d'abord.</p>
    );
  }
  if (error !== null) {
    return <p role="alert">Erreur de verdict : {error}</p>;
  }
  if (verdict === null) {
    return <p className="run-empty">{loading ? "Calcul du verdict..." : "Pas de verdict."}</p>;
  }
  const submittedStatus = submitResult?.judged[0]?.status ?? null;
  const dims: Array<[string, boolean]> = [
    ["Identite (I3)", verdict.dimensions.identity],
    ["Capabilities (declare vs reel)", verdict.dimensions.capabilities],
    ["Policy", verdict.dimensions.policy],
    ["Comportement", verdict.dimensions.behavior],
  ];
  const globalCls = verdict.verdict === "correct" ? "voyant-done" : "voyant-error";
  return (
    <div className="run-verdict" data-testid="run-verdict">
      <div className="run-verdict-head">
        <span className={`voyant ${globalCls}`}>
          <span className="voyant-dot" />
          {verdict.verdict}
        </span>
        <span className="run-verdict-count">
          {verdict.action_count} action(s) jugee(s)
        </span>
      </div>
      <ul className="run-verdict-dims">
        {dims.map(([label, ok]) => (
          <li key={label} className="run-verdict-dim">
            <span className={`voyant ${ok ? "voyant-done" : "voyant-error"}`}>
              <span className="voyant-dot" />
              {ok ? "conforme" : "violation"}
            </span>
            <span className="run-verdict-dim-label">{label}</span>
          </li>
        ))}
      </ul>
      {verdict.capability_violations.length > 0 && (
        <div className="run-verdict-violations">
          <h4>Violations de capabilities</h4>
          <ul>
            {verdict.capability_violations.map((vio, i) => (
              <li key={`${vio.observed_action}-${i}`} className="run-verdict-violation">
                <code className="mono">{vio.observed_action}</code>{" "}
                <span className="run-verdict-kind">{vio.kind}</span>
                <span className="run-verdict-note">{vio.note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="run-verdict-submit">
        <button
          type="button"
          className="btn-primary"
          disabled={submitting}
          onClick={onSubmit}
          data-testid="submit-verdict-btn"
          title="Juge ce run et le pousse sur le tableau Verdicts (comme un outil d'identification externe)"
        >
          {submitting ? "Soumission..." : "Soumettre aux Verdicts"}
        </button>
        {submitError !== null && (
          <span className="run-verdict-submit-error" role="alert">
            {submitError}
          </span>
        )}
        {submitResult !== null && submitError === null && (
          <span className="run-verdict-submit-ok" data-testid="submit-verdict-ok">
            Soumis ({submittedStatus}) -- <Link to="/verdicts">voir le tableau Verdicts</Link>
          </span>
        )}
      </div>
    </div>
  );
}

export default function AgentRunModal(props: AgentRunModalProps): JSX.Element | null {
  const {
    open,
    agentId,
    runId,
    status,
    runs = [],
    campaignId,
    steps = [],
    onClose,
    onPurge,
    fetchEvents = getRunEvents,
    socketFactory = openRunSocket,
    fetchVerdict = getRunVerdict,
    submitVerdict = submitRunVerdict,
    fetchTraces = (rid: string) => getProxyTraces(undefined, rid),
  } = props;

  const isCampaign = campaignId !== undefined;

  const framesRef = useRef<RunEvent[]>([]);
  const seenSeq = useRef<Set<number>>(new Set());
  const currentRun = useRef<string | null>(null);
  const [, setTick] = useState(0);
  const [live, setLive] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [purging, setPurging] = useState(false);
  const [tab, setTab] = useState<
    "steps" | "json" | "decide" | "journal" | "verdict" | "traces"
  >(campaignId !== undefined ? "steps" : "json");
  // Proxy traces of THIS run (deep-link from the eye).
  const [traces, setTraces] = useState<ProxyTrace[] | null>(null);
  const [tracesDebug, setTracesDebug] = useState<boolean>(true);
  const [tracesError, setTracesError] = useState<string | null>(null);
  const [tracesLoading, setTracesLoading] = useState(false);
  // Per-run frame log for the Journal tab: runId -> ordered frames.
  const [journal, setJournal] = useState<Record<string, RunEvent[]>>({});
  // F1 verdict state (fetched lazily when the Verdict tab opens).
  const [verdict, setVerdict] = useState<RunVerdict | null>(null);
  const [verdictError, setVerdictError] = useState<string | null>(null);
  const [verdictLoading, setVerdictLoading] = useState(false);
  // Submit-to-Verdicts-board state (the run pushed onto /verdicts).
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<RunVerdictSubmission | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || runId === null) {
      return;
    }
    if (currentRun.current !== runId) {
      currentRun.current = runId;
      framesRef.current = [];
      seenSeq.current = new Set();
      setError(null);
      // A new run invalidates any previous board submission.
      setSubmitResult(null);
      setSubmitError(null);
      setTick((n) => n + 1);
    }
    let alive = true;

    const append = (incoming: RunEvent[]): void => {
      if (!alive) {
        return;
      }
      let changed = false;
      for (const frame of incoming) {
        const seq = frameSeq(frame);
        if (seq !== null) {
          if (seenSeq.current.has(seq)) {
            continue;
          }
          seenSeq.current.add(seq);
        }
        framesRef.current.push(frame);
        changed = true;
      }
      if (changed) {
        setTick((n) => n + 1);
      }
    };

    fetchEvents(runId)
      .then(append)
      .catch((err: unknown) => {
        if (alive) {
          setError(err instanceof Error ? err.message : String(err));
        }
      });

    let socket: WebSocket | null = null;
    try {
      socket = socketFactory(runId);
      socket.onopen = () => alive && setLive(true);
      socket.onclose = () => alive && setLive(false);
      socket.onerror = () => alive && setLive(false);
      socket.onmessage = (message: MessageEvent) => {
        try {
          append([JSON.parse(message.data as string) as RunEvent]);
        } catch {
          // A malformed frame must never crash the viewer.
        }
      };
    } catch {
      // No live socket (run already gone); the snapshot still renders.
    }

    return () => {
      alive = false;
      socket?.close();
    };
  }, [open, runId, fetchEvents, socketFactory]);

  const frames = framesRef.current;
  const runState = deriveState(frames, status);
  // The runs this modal's history tab covers: a campaign's runs (by campaign_id)
  // in campaign mode, otherwise this agent's runs (by agent_id).
  const subjectRuns = runs.filter((r) =>
    isCampaign ? r.campaign_id === campaignId : r.agent_id === agentId,
  );
  const subjectRunIds = subjectRuns.map((r) => r.id).join(",");

  // When the Journal tab is open, fetch the frames of every run for this agent
  // so the log shows the detailed action history across ALL runs (it grows with
  // each relaunch). Only fetch runs not already loaded.
  useEffect(() => {
    if (!open || tab !== "journal") {
      return;
    }
    const missing = subjectRunIds.split(",").filter((id) => id !== "" && journal[id] === undefined);
    if (missing.length === 0) {
      return;
    }
    let alive = true;
    Promise.all(
      missing.map((id) =>
        fetchEvents(id)
          .then((ev) => [id, ev] as const)
          .catch(() => [id, [] as RunEvent[]] as const),
      ),
    ).then((pairs) => {
      if (!alive) {
        return;
      }
      setJournal((prev) => {
        const next = { ...prev };
        for (const [id, ev] of pairs) {
          next[id] = ev;
        }
        return next;
      });
    });
    return () => {
      alive = false;
    };
  }, [open, tab, subjectRunIds, journal, fetchEvents]);

  // F1: judge the current run against its declared manifest when the Verdict
  // tab opens. Refetched per run; read-model, never mutates anything (I1).
  useEffect(() => {
    if (!open || tab !== "verdict" || runId === null) {
      return;
    }
    let alive = true;
    setVerdictLoading(true);
    setVerdictError(null);
    fetchVerdict(runId)
      .then((v) => {
        if (alive) {
          setVerdict(v);
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          setVerdictError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (alive) {
          setVerdictLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [open, tab, runId, fetchVerdict]);

  // Deep-link: load THIS run's proxy traces when the Traces tab opens (F3).
  useEffect(() => {
    if (!open || tab !== "traces" || runId === null) {
      return;
    }
    let alive = true;
    setTracesLoading(true);
    setTracesError(null);
    fetchTraces(runId)
      .then((res) => {
        if (alive) {
          setTraces(res.traces);
          setTracesDebug(res.debug_enabled);
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          setTracesError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (alive) {
          setTracesLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [open, tab, runId, fetchTraces]);

  const journalTotalLines = subjectRuns.reduce(
    (n, r) => n + (journal[r.id]?.length ?? 0),
    0,
  );

  const value = JSON.stringify(
    {
      agent_id: agentId,
      run_id: runId,
      state: runState,
      live,
      frame_count: frames.length,
      frames,
    },
    null,
    2,
  );

  const onSubmitVerdict = async (): Promise<void> => {
    if (runId === null) {
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      setSubmitResult(await submitVerdict(runId));
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const purge = async (): Promise<void> => {
    if (onPurge === undefined) {
      return;
    }
    setPurging(true);
    try {
      await onPurge(agentId);
    } finally {
      setPurging(false);
    }
  };

  if (!open) {
    return null;
  }

  return (
    <HelpModal
      open={open}
      title={
        isCampaign
          ? `Campagne ${campaignId} -- ${runState}`
          : `Agent ${agentId} -- ${runState}`
      }
      onClose={onClose}
    >
      <div className="run-tabs" role="tablist">
        {isCampaign && (
          <button
            type="button"
            role="tab"
            aria-selected={tab === "steps"}
            className={tab === "steps" ? "run-tab run-tab-active" : "run-tab"}
            onClick={() => setTab("steps")}
          >
            Etapes (agents)
          </button>
        )}
        <button
          type="button"
          role="tab"
          aria-selected={tab === "json"}
          className={tab === "json" ? "run-tab run-tab-active" : "run-tab"}
          onClick={() => setTab("json")}
        >
          Run courant (JSON)
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "journal"}
          className={tab === "journal" ? "run-tab run-tab-active" : "run-tab"}
          onClick={() => setTab("journal")}
        >
          Historique des runs ({subjectRuns.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "decide"}
          className={tab === "decide" ? "run-tab run-tab-active" : "run-tab"}
          onClick={() => setTab("decide")}
        >
          Decide {"->"} Action
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "verdict"}
          className={tab === "verdict" ? "run-tab run-tab-active" : "run-tab"}
          onClick={() => setTab("verdict")}
        >
          Verdict recette
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "traces"}
          className={tab === "traces" ? "run-tab run-tab-active" : "run-tab"}
          onClick={() => setTab("traces")}
        >
          Traces proxy
        </button>
        {live && <span className="run-live">en direct</span>}
      </div>

      {tab === "steps" ? (
        <CampaignStepsView entries={groupSteps(frames, steps)} runId={runId} />
      ) : tab === "traces" ? (
        <RunTracesView
          runId={runId}
          loading={tracesLoading}
          error={tracesError}
          debugEnabled={tracesDebug}
          traces={traces}
        />
      ) : tab === "decide" ? (
        <DecideView runId={runId} frames={frames} />
      ) : tab === "verdict" ? (
        <RunVerdictView
          runId={runId}
          loading={verdictLoading}
          error={verdictError}
          verdict={verdict}
          onSubmit={() => void onSubmitVerdict()}
          submitting={submitting}
          submitResult={submitResult}
          submitError={submitError}
        />
      ) : tab === "json" ? (
        runId === null ? (
          <p className="run-empty">
            Aucun run courant. Lance l'agent pour voir ses frames ici.
          </p>
        ) : error !== null ? (
          <p role="alert">Erreur de chargement du run : {error}</p>
        ) : (
          <Suspense fallback={<p>Chargement de l'editeur...</p>}>
            <MonacoJsonViewer value={value} />
          </Suspense>
        )
      ) : (
        <div className="run-log-wrap" data-testid="run-journal">
          <div className="run-log-bar">
            <p className="run-log-caption">
              {subjectRuns.length} run(s), {journalTotalLines} ligne(s) de log
              (le plus recent en haut). Grandit a chaque relance.
            </p>
            {onPurge !== undefined && (
              <button
                type="button"
                className="btn-danger"
                disabled={purging || subjectRuns.length === 0}
                onClick={() => void purge()}
                title="Vide les runs termines de cet agent (n'affecte pas l'audit, I1)"
              >
                {purging ? "Purge..." : "Purger"}
              </button>
            )}
          </div>
          {subjectRuns.length === 0 ? (
            <p className="run-empty" data-testid="run-journal-empty">
              {isCampaign ? "Aucun run pour cette campagne." : "Aucun run pour cet agent."}
            </p>
          ) : (
            subjectRuns.map((run) => {
              const v = voyantFor(run.status);
              const lines = journal[run.id];
              const ts = run.created_at
                ? run.created_at.replace("T", " ").replace("+00:00", "Z")
                : "-";
              return (
                <div key={run.id} className="run-group" data-testid="run-journal-row">
                  <div className="run-group-head">
                    <span className="mono run-group-id">{run.id.slice(0, 12)}</span>
                    <span className="mono run-log-ts">{ts}</span>
                    <span className={`voyant ${v.cls}`}>
                      <span className="voyant-dot" />
                      {v.label}
                    </span>
                    {run.error && <span className="run-log-err">{run.error}</span>}
                  </div>
                  {lines === undefined ? (
                    <p className="run-empty">Chargement du log...</p>
                  ) : lines.length === 0 ? (
                    <p className="run-empty">Aucune frame pour ce run.</p>
                  ) : (
                    <ol className="run-log">
                      {lines.map((frame, i) => {
                        const line = frameToLine(frame);
                        return (
                          <li
                            key={line.seq ?? `i${i}`}
                            className={`run-log-line tone-${line.tone}`}
                          >
                            <span className="run-log-seq">{line.seq ?? "-"}</span>
                            <span className="run-log-kind">{line.kind}</span>
                            <span className="run-log-text">{line.text}</span>
                          </li>
                        );
                      })}
                    </ol>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </HelpModal>
  );
}
