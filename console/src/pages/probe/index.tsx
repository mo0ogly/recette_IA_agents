/**
 * Probe menu: the discoveryprobe eBPF reference capture (design 12.6).
 *
 * Launches a bounded eBPF capture through the non-privileged API
 * (POST /probe/capture -> broker, CAP_BPF), then shows -- per agent and per
 * observation surface -- what RailNode SAW. An agent seen on no surface is a
 * false negative rendered in prominent red: the thesis failure ("si l'outil ne
 * voit pas les agents, c'est un echec"). Read-only beyond the capture trigger;
 * the judge is deterministic (I4).
 */

import { useEffect, useMemo, useState } from "react";
import { captureProbe, getProbeStatus } from "../../api/client";
import type { ProbeCaptureResult, SurfaceRecording } from "../../api/client";
import "./probe.css";

/** The four observation surfaces, in the order RailNode is reasoned about. */
const SURFACE_ORDER = ["hook_subprocess", "hook_mcp", "hook_sdk", "ebpf_wire"] as const;
const SURFACE_LABEL: Record<string, string> = {
  hook_subprocess: "hook subprocess",
  hook_mcp: "hook MCP",
  hook_sdk: "hook SDK",
  ebpf_wire: "eBPF wire",
};

const DEFAULT_AGENTS = "pr-bot-sdk, ghost-direct-db";

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
  const [agentsInput, setAgentsInput] = useState(DEFAULT_AGENTS);
  const [durationMs, setDurationMs] = useState(3000);
  const [result, setResult] = useState<ProbeCaptureResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    let alive = true;
    getProbeStatus()
      .then((s) => alive && setConfigured(s.configured))
      .catch(() => alive && setConfigured(false));
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

  return (
    <section className="probe-page">
      <h1>Probe eBPF</h1>
      <p className="probe-note">
        Capture bornee via la sonde de reference (eBPF, CAP_BPF cote broker). Prouve
        ce que RailNode VOIT d&apos;un agent simule, surface par surface -- meme dans
        un conteneur (un seul kernel). Un agent vu nulle part est un echec de la
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
          disabled={capturing || configured === false || agents.length === 0}
          data-testid="probe-capture-button"
        >
          {capturing ? "Capture..." : "Capturer"}
        </button>
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
        </>
      )}
    </section>
  );
}
