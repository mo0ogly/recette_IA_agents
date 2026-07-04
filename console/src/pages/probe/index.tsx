/**
 * Probe menu: the discoveryprobe eBPF reference capture (design 12.6).
 *
 * Launches a bounded eBPF capture through the non-privileged API
 * (POST /probe/capture -> broker, CAP_BPF), then shows -- per agent and per
 * observation surface -- what the discovery probe SAW. An agent seen on no surface is a
 * false negative rendered in prominent red: the thesis failure ("si l'outil ne
 * voit pas les agents, c'est un echec"). Read-only beyond the capture trigger;
 * the judge is deterministic (I4).
 */

import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { captureProbe, getInventory, getLlmTraces, getProbeStatus } from "../../api/client";
import type {
  AgentInventory,
  LlmTrace,
  ProbeCaptureResult,
  SurfaceRecording,
} from "../../api/client";
import LlmTracePanel from "./LlmTracePanel";
import AgentAnalysisPanel from "./AgentAnalysisPanel";
import BehaviorWavePanel from "./BehaviorWavePanel";
import CorrelationPanel from "./CorrelationPanel";
import InventoryPanel from "./InventoryPanel";
import PageHelp from "../../components/help/PageHelp";
import "./probe.css";

// Lazy so the monaco-editor payload stays out of the base bundle (same posture
// as FluxAnalyzer). The viewer renders the raw recording JSON the probe returned.
const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));

/** The four observation surfaces, in the order the discovery probe is reasoned about. */
const SURFACE_ORDER = ["hook_subprocess", "hook_mcp", "hook_sdk", "ebpf_wire"] as const;
const SURFACE_LABEL: Record<string, string> = {
  hook_subprocess: "hook subprocess",
  hook_mcp: "hook MCP",
  hook_sdk: "hook SDK",
  ebpf_wire: "eBPF wire",
};

const DEFAULT_AGENTS = "pr-bot-sdk, ghost-direct-db";

/** Pause between successive live capture windows (ms). */
const LIVE_GAP_MS = 250;

function parseAgents(raw: string): string[] {
  return raw
    .split(",")
    .map((a) => a.trim())
    .filter((a) => a.length > 0);
}

function AgentCard({ recording }: { recording: SurfaceRecording }): JSX.Element {
  const seenAnywhere = SURFACE_ORDER.some(
    (s) => (recording.surfaces[s]?.length ?? 0) > 0,
  );
  return (
    <article
      className={`probe-agent ${seenAnywhere ? "" : "probe-agent-ghost"}`}
      data-testid={`probe-agent-${recording.agent_id}`}
    >
      <header className="probe-agent-head">
        <span className="probe-agent-id">{recording.agent_id}</span>
        <span
          className={`probe-chip ${seenAnywhere ? "probe-chip-ok" : "probe-chip-fail"}`}
        >
          {seenAnywhere ? "vu" : "vu nulle part"}
        </span>
      </header>
      <ul className="probe-surfaces">
        {SURFACE_ORDER.map((surface) => {
          const visible = recording.surfaces[surface] ?? [];
          const on = visible.length > 0;
          return (
            <li
              key={surface}
              className={`probe-surface ${on ? "probe-surface-on" : "probe-surface-off"}`}
              data-testid={`probe-surface-${recording.agent_id}-${surface}`}
            >
              <span className="probe-surface-name">{SURFACE_LABEL[surface]}</span>
              {on ? (
                <span className="probe-surface-keys">{visible.join(", ")}</span>
              ) : (
                <span className="probe-surface-blind">aveugle</span>
              )}
            </li>
          );
        })}
      </ul>
    </article>
  );
}

export default function ProbePage(): JSX.Element {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [mode, setMode] = useState<string>("off");
  const [agentsInput, setAgentsInput] = useState(DEFAULT_AGENTS);
  const [durationMs, setDurationMs] = useState(3000);
  const [result, setResult] = useState<ProbeCaptureResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [runId, setRunId] = useState("");
  const [traces, setTraces] = useState<LlmTrace[] | null>(null);
  // Live mode: repeat bounded captures, streaming each window into the view.
  const [live, setLive] = useState(false);
  const [windowCount, setWindowCount] = useState(0);
  const [showRaw, setShowRaw] = useState(false);
  // Static agent inventory (discoveryprobe-inventory): passports + comm graph.
  // Independent of a live capture (a static scan), fetched once on mount.
  const [inventory, setInventory] = useState<AgentInventory | null>(null);

  useEffect(() => {
    let alive = true;
    getProbeStatus()
      .then((s) => {
        if (!alive) return;
        setConfigured(s.configured);
        setMode(s.mode);
      })
      .catch(() => alive && setConfigured(false));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    getInventory()
      .then((inv) => alive && setInventory(inv))
      .catch(() => alive && setInventory(null));
    return () => {
      alive = false;
    };
  }, []);

  const agents = useMemo(() => parseAgents(agentsInput), [agentsInput]);
  const card = result?.scorecard;
  const recordings = result?.recording.recordings ?? [];
  const sha = result?.recording.recording_sha256;

  function runCapture(): void {
    setCapturing(true);
    setError(null);
    captureProbe({ agents, duration_ms: durationMs })
      .then((r) => {
        setResult(r);
        setCapturing(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setCapturing(false);
      });
  }

  // LIVE mode: the broker is batch (one bounded capture per request), so "live"
  // here means SUCCESSIVE bounded windows, each streamed into the view as it
  // lands -- NOT a per-event eBPF stream (honest labelling, R13/R14). The loop
  // chains one capture after the previous resolves (never overlapping) and stops
  // on toggle-off, error, or unmount.
  const liveRef = useRef(false);
  useEffect(() => {
    liveRef.current = live;
    if (!live) {
      return;
    }
    let cancelled = false;
    async function pump(): Promise<void> {
      while (!cancelled && liveRef.current) {
        try {
          const r = await captureProbe({ agents, duration_ms: durationMs });
          if (cancelled) {
            return;
          }
          setResult(r);
          setWindowCount((n) => n + 1);
          setError(null);
        } catch (e) {
          if (!cancelled) {
            setError(e instanceof Error ? e.message : String(e));
            setLive(false);
          }
          return;
        }
        // Small gap between windows: yields to the event loop (so Stop is
        // responsive) and avoids a tight loop if the broker ever returns
        // instantly. The real capture already blocks for duration_ms.
        await new Promise((resolve) => setTimeout(resolve, LIVE_GAP_MS));
      }
    }
    void pump();
    return () => {
      cancelled = true;
    };
    // agents/durationMs are read fresh each iteration; re-arm only on live toggle
    // and the window size so a mid-run change takes effect on the next window.
  }, [live, durationMs, agentsInput]);

  function loadTraces(): void {
    getLlmTraces(runId)
      .then((r) => setTraces(r.traces))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  return (
    <section className="probe-page">
      <div className="page-head">
        <h1>Probe eBPF</h1>
        {configured && (
          <span
            className={`probe-chip ${mode === "live" ? "probe-chip-ok" : "probe-chip-replay"}`}
            data-testid="probe-mode"
          >
            {mode === "live" ? "mode live (eBPF)" : "mode replay (reference)"}
          </span>
        )}
        <PageHelp topic="probe" />
      </div>
      {configured && mode === "replay" && (
        <p className="probe-note probe-replay-note" data-testid="probe-replay-note">
          Mode replay : la capture rejoue l&apos;etat de surface fige du corpus
          (corpus/surface), de maniere deterministe (I4) -- ce n&apos;est PAS une
          capture eBPF live. La preuve live sous CAP_BPF reste le role de la sonde
          native.
        </p>
      )}
      <p className="probe-note">
        Capture bornee via la sonde de reference (eBPF, CAP_BPF cote broker). Prouve
        ce que la sonde discovery VOIT d&apos;un agent simule, surface par surface -- meme
        dans un conteneur (un seul kernel). Un agent vu nulle part est un echec de la
        these.
      </p>

      {configured === false && (
        <div className="probe-offline" role="status" data-testid="probe-offline">
          Broker de capture non lance. Demarrez-le via <code>recette.sh</code>{" "}
          (variable <code>INSPECT_IA_AGENTS_PROBE_SOCKET</code>). La capture reste
          desactivee.
        </div>
      )}

      <div className="probe-control">
        <label className="probe-field">
          <span className="probe-field-label">Agents (ids, separes par virgule)</span>
          <input
            className="probe-input"
            value={agentsInput}
            onChange={(e) => setAgentsInput(e.target.value)}
            data-testid="probe-agents-input"
          />
        </label>
        <label className="probe-field probe-field-narrow">
          <span className="probe-field-label">Fenetre</span>
          <select
            className="probe-input"
            value={durationMs}
            onChange={(e) => setDurationMs(Number(e.target.value))}
            data-testid="probe-duration-select"
          >
            <option value={1000}>1 s</option>
            <option value={3000}>3 s</option>
            <option value={5000}>5 s</option>
            <option value={10000}>10 s</option>
          </select>
        </label>
        <button
          type="button"
          className="probe-button"
          onClick={runCapture}
          disabled={capturing || live || configured === false || agents.length === 0}
          data-testid="probe-capture-button"
        >
          {capturing ? "Capture..." : "Capturer"}
        </button>
        <button
          type="button"
          className={`probe-button ${live ? "probe-button-live" : ""}`}
          onClick={() => {
            if (!live) {
              setWindowCount(0);
            }
            setLive((on) => !on);
          }}
          disabled={configured === false || agents.length === 0}
          data-testid="probe-live-button"
        >
          {live ? "Stop live" : "Live"}
        </button>
        {live && (
          <span className="probe-chip probe-chip-ok" data-testid="probe-live-indicator">
            live -- fenetre {windowCount} ({durationMs} ms)
          </span>
        )}
      </div>

      {error && (
        <div className="probe-error" role="alert" data-testid="probe-error">
          {error}
        </div>
      )}

      {result && (
        <>
          <div
            className={`probe-hero ${card?.ok ? "probe-hero-ok" : "probe-hero-fail"}`}
            data-testid="probe-hero"
          >
            <span className="probe-hero-verdict">{card?.ok ? "VU" : "ANGLE MORT"}</span>
            <span className="probe-hero-detail">
              {card
                ? `${card.total_agents - card.false_negatives.length}/${card.total_agents} agents vus`
                : result.recording.reason || "capture refusee"}
            </span>
            {sha && <span className="probe-hero-sha">sha256 {sha.slice(0, 12)}…</span>}
          </div>

          {card && card.false_negatives.length > 0 && (
            <div className="probe-fn" role="alert" data-testid="probe-false-negatives">
              <span className="probe-fn-label">Vus nulle part</span>
              <span className="probe-fn-list">{card.false_negatives.join(", ")}</span>
            </div>
          )}

          <div className="probe-agents" data-testid="probe-agents">
            {recordings.map((rec) => (
              <AgentCard key={rec.agent_id} recording={rec} />
            ))}
          </div>

          <AgentAnalysisPanel analysis={result.agent_analysis} />

          <BehaviorWavePanel recording={result.recording} />

          <CorrelationPanel recording={result.recording} />

          <div className="probe-raw-head">
            <h2 className="probe-subtitle">Recording brut (ce que la sonde a vu)</h2>
            <button
              type="button"
              className="probe-button probe-button-ghost"
              onClick={() => setShowRaw((s) => !s)}
              data-testid="probe-raw-toggle"
            >
              {showRaw ? "Masquer le JSON" : "Voir le JSON brut"}
            </button>
          </div>
          {showRaw && (
            <div className="probe-raw" data-testid="probe-raw">
              <Suspense fallback={<div className="probe-note">chargement de l'editeur...</div>}>
                <MonacoJsonViewer
                  value={JSON.stringify(result.recording, null, 2)}
                  height="40vh"
                />
              </Suspense>
            </div>
          )}
        </>
      )}

      <h2 className="probe-subtitle">Inventaire des agents (scan statique)</h2>
      <p className="probe-note">
        Ce que le scan statique DECLARE : chaque agent identifie, son passeport
        (present / absent / invalide), ses violations, et le graphe de
        communication (aretes declarees vs observees, handoffs non declares en
        rouge, sauts via passerelle a part). Independant d&apos;une capture live.
      </p>
      <InventoryPanel inventory={inventory} />

      <h2 className="probe-subtitle">Trace LLM (surface hook in-process)</h2>
      <p className="probe-note">
        L&apos;autre surface : ce que l&apos;agent a DECIDE in-process (intention +
        tokens + latence), capture par le hook. Reconcilie avec la surface eBPF
        ci-dessus -- un agent vu ici mais absent du wire (ou l&apos;inverse) est la
        divergence qui revele un ghost.
      </p>
      <div className="probe-control">
        <label className="probe-field">
          <span className="probe-field-label">Run id</span>
          <input
            className="probe-input"
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            data-testid="probe-run-input"
          />
        </label>
        <button
          type="button"
          className="probe-button"
          onClick={loadTraces}
          disabled={runId.length === 0}
          data-testid="probe-traces-button"
        >
          Voir traces
        </button>
      </div>
      {traces !== null && <LlmTracePanel traces={traces} />}
    </section>
  );
}
