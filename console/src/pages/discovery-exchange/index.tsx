/**
 * Discovery x Echange -- overlay the discovery verdict on the REAL exchange.
 *
 * Two columns: LEFT the real agent<->server exchange (the proxy hook traces +
 * wire flows, one row per exchange with an identified/ghost badge); RIGHT what
 * the discovery core SAW -- per-agent detection (DETECTE/GHOST + surfaces) and
 * the ghost-exchange count (wire-only traffic discovery could not attribute to
 * any identified agent). Read-only (I1).
 *
 * Source of the verdict: the deterministic surface ORACLE by default
 * (GET /proxy/discovery-exchange, always available, no CAP_BPF); the real eBPF
 * broker capture when it is configured (captureProbe) -- the toggle is disabled
 * with a note when the broker is off (fail-safe). A run filter narrows the view
 * client-side. Polls every 2s like the proxy console.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  captureProbe,
  getDiscoveryExchange,
  getProbeMonitor,
  getProbeStatus,
  launchProcessRun,
  listAgents,
  listCampaigns,
  processCapture,
  processCaptureCampaign,
  runCampaign,
  setProxyDebug,
  startProbeMonitor,
  stopProbeMonitor,
} from "../../api/client";
import type {
  DetectionScorecard,
  ProbeMonitorState,
  ProbeStatus,
  WireEndpoint,
} from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import type { AgentConfig, Campaign, ExchangeReport } from "../../types/platform";
import {
  agentOutcome,
  agentsForRun,
  detectedSurfaces,
  distinctRuns,
  exchangeToLine,
  filterByRun,
  ghostCount,
} from "./exchangeModel";
import "./discovery-exchange.css";

const POLL_INTERVAL_MS = 2000;

type Source = "oracle" | "ebpf";

export default function DiscoveryExchangePage(): JSX.Element {
  const [report, setReport] = useState<ExchangeReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<Source>("oracle");
  const [runId, setRunId] = useState("");
  const [probe, setProbe] = useState<ProbeStatus | null>(null);
  const [ebpfCard, setEbpfCard] = useState<DetectionScorecard | null>(null);
  const [ebpfError, setEbpfError] = useState<string | null>(null);
  // v1 named-wire annotation from the last eBPF capture: per-agent connect
  // endpoints resolved to their DECLARED server name + the undeclared hosts.
  const [wireNamed, setWireNamed] = useState<Record<string, WireEndpoint[]>>({});
  const [undeclaredHosts, setUndeclaredHosts] = useState<string[]>([]);
  // Process-mode launch (eBPF-observable): mock agents that can run as their own
  // OS process so the kernel tracepoints (eBPF source) can attribute them.
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [procAgent, setProcAgent] = useState("");
  const [launchMsg, setLaunchMsg] = useState<string | null>(null);
  // Campaign launch (eBPF-observable): spawn every campaign step as a process,
  // capture the whole campaign by PID in one window.
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campId, setCampId] = useState("");
  const [campMsg, setCampMsg] = useState<string | null>(null);
  // Passive eBPF watch: agents seen on the wire in near-real-time (no per-capture click).
  const [monitor, setMonitor] = useState<ProbeMonitorState | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setReport(await getDiscoveryExchange());
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    getProbeStatus()
      .then(setProbe)
      .catch(() => setProbe(null));
    listAgents()
      .then((a) => setAgents(a.filter((x) => (x.ai_mode ?? "mock") !== "real" && x.scenario)))
      .catch(() => setAgents([]));
    listCampaigns()
      .then(setCampaigns)
      .catch(() => setCampaigns([]));
    const pollMonitor = (): void => {
      getProbeMonitor()
        .then(setMonitor)
        .catch(() => setMonitor(null));
    };
    pollMonitor();
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    const monTimer = setInterval(pollMonitor, POLL_INTERVAL_MS);
    return () => {
      clearInterval(timer);
      clearInterval(monTimer);
    };
  }, [refresh]);

  const toggleMonitor = useCallback(async (): Promise<void> => {
    try {
      if (monitor?.running) {
        await stopProbeMonitor();
      } else {
        await startProbeMonitor();
      }
      setMonitor(await getProbeMonitor());
    } catch (e: unknown) {
      setEbpfError(e instanceof Error ? e.message : String(e));
    }
  }, [monitor]);

  const brokerLive = probe?.configured === true;

  // The oracle exchange view is fed by the ProxyTrace recorder, which only
  // fills when side-effect tracing is ON. It is OFF by default, so a governed
  // campaign run (mock agent, no server) executes for real -- recordings + audit
  // -- yet leaves this column empty. That reads as "nothing happened"; it is
  // not. Surface the toggle so the operator can turn tracing on and re-launch,
  // instead of staring at a silent empty table.
  const tracingOff = report !== null && report.debug_enabled === false;

  const enableTracing = useCallback(async (): Promise<void> => {
    try {
      await setProxyDebug(true);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [refresh]);

  const launchProc = useCallback(async (): Promise<void> => {
    if (!procAgent) return;
    setLaunchMsg(null);
    setEbpfError(null);
    if (brokerLive) {
      // Precise: spawn the agent as its own process and capture it by the
      // child's exact PID (no reliance on the 15-byte comm). One coordinated
      // backend call (spawn + pid capture + score).
      try {
        const res = await processCapture(procAgent);
        setEbpfCard(res.scorecard ?? null);
        setWireNamed(res.wire_named ?? {});
        setUndeclaredHosts(res.undeclared_hosts ?? []);
        setEbpfError(res.scorecard ? null : `broker: ${res.recording.status}`);
        setSource("ebpf");
        setLaunchMsg(`process capture (pid): ${procAgent}`);
      } catch (e: unknown) {
        setLaunchMsg(`echec: ${e instanceof Error ? e.message : String(e)}`);
      }
      return;
    }
    // No broker: just launch the process run (oracle-only view).
    try {
      const run = await launchProcessRun(procAgent);
      setLaunchMsg(`process lance: ${procAgent} (run ${run.run_id.slice(0, 8)})`);
    } catch (e: unknown) {
      setLaunchMsg(`echec: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [procAgent, brokerLive]);

  const launchCamp = useCallback(async (): Promise<void> => {
    if (!campId) return;
    setCampMsg(null);
    setEbpfError(null);
    if (brokerLive) {
      // Spawn every campaign step as a process and capture the whole campaign by
      // PID in one eBPF window; surface the aggregate scorecard (ghosts included).
      try {
        const res = await processCaptureCampaign(campId);
        setEbpfCard(res.scorecard ?? null);
        setWireNamed(res.wire_named ?? {});
        setUndeclaredHosts(res.undeclared_hosts ?? []);
        setEbpfError(res.scorecard ? null : `broker: ${res.recording.status}`);
        setSource("ebpf");
        const skip = res.skipped.length ? `, ${res.skipped.length} ignore(s)` : "";
        setCampMsg(`campagne capturee: ${res.agents.length} agent(s)${skip}`);
      } catch (e: unknown) {
        setCampMsg(`echec: ${e instanceof Error ? e.message : String(e)}`);
      }
      return;
    }
    // No broker: run the campaign in-process (oracle-only view).
    try {
      const run = await runCampaign(campId);
      setCampMsg(`campagne lancee: ${campId} (run ${run.run_id.slice(0, 8)})`);
    } catch (e: unknown) {
      setCampMsg(`echec: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [campId, brokerLive]);

  const exchanges = useMemo(() => report?.exchanges ?? [], [report]);
  const runOptions = useMemo(() => distinctRuns(exchanges), [exchanges]);
  const shownExchanges = useMemo(() => filterByRun(exchanges, runId), [exchanges, runId]);
  const lines = useMemo(() => shownExchanges.map(exchangeToLine), [shownExchanges]);
  const ghosts = useMemo(() => ghostCount(shownExchanges), [shownExchanges]);
  const shownAgents = useMemo(
    () => agentsForRun(report?.agents ?? [], exchanges, runId),
    [report, exchanges, runId],
  );

  const agentIds = useMemo(() => (report?.agents ?? []).map((a) => a.agent_id), [report]);
  const brokerReady = probe?.configured === true;
  const showEbpf = source === "ebpf" && ebpfCard !== null;

  const runEbpf = useCallback(async (): Promise<void> => {
    if (!brokerReady || agentIds.length === 0) return;
    try {
      const res = await captureProbe({ agents: agentIds });
      setEbpfCard(res.scorecard ?? null);
      setWireNamed(res.wire_named ?? {});
      setUndeclaredHosts(res.undeclared_hosts ?? []);
      setEbpfError(res.scorecard ? null : `broker: ${res.recording.status}`);
    } catch (e: unknown) {
      setEbpfError(e instanceof Error ? e.message : String(e));
    }
  }, [brokerReady, agentIds]);

  return (
    <section className="page dx-page">
      <div className="page-head">
        <h1>Discovery x Echange</h1>
        <PageHelp topic="discovery_exchange" />
        <AssistButton topic="dashboard.overview" label="Discovery x Echange" />
        {report !== null && (
          <span
            className={`dx-ghost dx-ghost-${ghosts === 0 ? "ok" : "alert"}`}
            data-testid="dx-ghost-count"
            title="Echanges wire-only que discovery n'a pu rattacher a aucun agent identifie"
          >
            {ghosts} echange(s) ghost
          </span>
        )}
      </div>
      <p className="dx-note">
        Superpose ce que le <strong>discovery</strong> a vu sur l&apos;
        <strong>echange reel</strong> agent &lt;-&gt; serveur. A gauche le trafic reel (hook +
        wire), a droite le verdict : chaque agent <strong>detecte</strong> (et sur quelles
        surfaces) ou <strong>ghost</strong>, et chaque echange <strong>identifie</strong> ou
        wire-only. Lecture seule.
      </p>

      <div className="dx-controls">
        <div className="dx-source" role="group" aria-label="source du verdict">
          <button
            type="button"
            className="dx-source-btn"
            data-active={source === "oracle"}
            onClick={() => setSource("oracle")}
          >
            Oracle (defaut)
          </button>
          <button
            type="button"
            className="dx-source-btn"
            data-active={source === "ebpf"}
            disabled={!brokerReady}
            title={brokerReady ? undefined : "broker eBPF non configure"}
            onClick={() => {
              setSource("ebpf");
              void runEbpf();
            }}
          >
            eBPF {probe ? `(${probe.mode})` : ""}
          </button>
          {source === "ebpf" && !brokerReady && (
            <span className="dx-source-note">
              broker eBPF indisponible -- oracle reste la source
            </span>
          )}
        </div>
        <label className="dx-filter-label">
          run
          <select
            className="dx-filter-input"
            data-testid="dx-run-filter"
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
          >
            <option value="">tous</option>
            {runOptions.map((r) => (
              <option key={r} value={r}>
                {r.slice(0, 12)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="dx-launch" role="group" aria-label="lancer en mode process">
        <span className="dx-launch-title">Mode process (eBPF)</span>
        <select
          className="dx-filter-input"
          data-testid="dx-proc-agent"
          aria-label="agent process"
          value={procAgent}
          onChange={(e) => setProcAgent(e.target.value)}
        >
          <option value="">agent...</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.id}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="dx-source-btn"
          data-testid="dx-launch-proc"
          disabled={!procAgent}
          onClick={() => void launchProc()}
        >
          Lancer (process)
        </button>
        <span className="dx-launch-note">
          lance l&apos;agent comme process OS -&gt; observable par la capture eBPF (toggle ci-dessus)
        </span>
        {launchMsg !== null && (
          <span className="dx-launch-msg" data-testid="dx-launch-msg">
            {launchMsg}
          </span>
        )}
      </div>

      <div className="dx-launch" role="group" aria-label="lancer une campagne en mode process">
        <span className="dx-launch-title">Campagne (eBPF)</span>
        <select
          className="dx-filter-input"
          data-testid="dx-camp"
          aria-label="campagne process"
          value={campId}
          onChange={(e) => setCampId(e.target.value)}
        >
          <option value="">campagne...</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id} ({c.steps.length})
            </option>
          ))}
        </select>
        <button
          type="button"
          className="dx-source-btn"
          data-testid="dx-launch-camp"
          disabled={!campId}
          onClick={() => void launchCamp()}
        >
          Lancer (campagne)
        </button>
        <span className="dx-launch-note">
          lance tous les agents de la campagne comme process OS -&gt; capture eBPF par PID en une fenetre
        </span>
        {campMsg !== null && (
          <span className="dx-launch-msg" data-testid="dx-camp-msg">
            {campMsg}
          </span>
        )}
      </div>

      <div className="dx-monitor" role="group" aria-label="surveillance ebpf live">
        <span className="dx-launch-title">Surveillance eBPF (live)</span>
        <button
          type="button"
          className="dx-source-btn"
          data-testid="dx-monitor-toggle"
          data-active={monitor?.running === true}
          onClick={() => void toggleMonitor()}
        >
          {monitor?.running ? "Arreter" : "Demarrer"}
        </button>
        <span className="dx-launch-note">
          veille passive : tout agent surveille qui se connecte est flague ici, sans capture manuelle
        </span>
        {monitor !== null && (
          <span className="dx-monitor-status" data-testid="dx-monitor-status">
            {monitor.running ? `actif (${monitor.windows} fenetre(s))` : "arrete"}
            {monitor.last_error ? ` -- ${monitor.last_error}` : ""}
          </span>
        )}
        {monitor !== null && monitor.sightings.length > 0 && (
          <ul className="dx-sightings" data-testid="dx-sightings">
            {monitor.sightings.map((s) => (
              <li key={s.agent_id} className="dx-agent" data-testid={`sighting-${s.agent_id}`}>
                <span className="dx-agent-id">{s.agent_id}</span>
                <span className="dx-badge dx-badge-identifie">VU</span>
                <span className="dx-surfaces">
                  {s.surfaces.join(", ")} ({s.windows_seen}x)
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error !== null && <p className="dx-error">{error}</p>}

      <div className="dx-grid">
        <section className="dx-col" aria-label="echange reel">
          <h2 className="dx-col-title">Echange reel</h2>
          {report !== null && lines.length === 0 && tracingOff ? (
            <div className="dx-empty" data-testid="dx-tracing-off">
              <p>
                <strong>Le tracage reseau des echanges est desactive.</strong> Une
                campagne (agent mock, sans serveur) s&apos;execute bien -- son
                verdict et ses actions sont visibles dans l&apos;onglet{" "}
                <strong>Campagnes</strong> (icone oeil) et <strong>Enregistrements</strong>{" "}
                -- mais les echanges reseau ne sont enregistres ici que lorsque le
                tracage est actif (variable INSPECT_IA_AGENTS_PROXY_DEBUG).
              </p>
              <p>
                Active le tracage puis <strong>relance la campagne</strong> : les
                runs anterieurs ne sont pas traces retroactivement.
              </p>
              <button
                type="button"
                className="dx-source-btn"
                data-testid="dx-enable-tracing"
                onClick={() => void enableTracing()}
              >
                Activer le tracage des echanges
              </button>
            </div>
          ) : report !== null && lines.length === 0 ? (
            <p className="dx-empty">
              Aucun echange -- lance un agent (les effets de bord sont traces ici).
            </p>
          ) : (
            <table className="dx-table" data-testid="exchange-table">
              <thead>
                <tr>
                  <th>seq</th>
                  <th>vue</th>
                  <th>echange</th>
                  <th>discovery</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={`${l.kind}-${l.seq}`} data-outcome={l.outcome}>
                    <td className="dx-num">#{l.seq}</td>
                    <td className="dx-kind">{l.kind}</td>
                    <td className="dx-label">{l.label}</td>
                    <td>
                      <span
                        className={`dx-badge dx-badge-${l.outcome}`}
                        data-testid="exchange-outcome"
                      >
                        {l.outcome}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="dx-col" aria-label="ce que discovery a vu">
          <h2 className="dx-col-title">
            Discovery a vu {showEbpf && <span className="dx-src-tag">(eBPF {probe?.mode})</span>}
          </h2>
          {ebpfError !== null && <p className="dx-error">{ebpfError}</p>}
          {showEbpf && ebpfCard !== null ? (
            // eBPF source: the broker capture can surface a ghost AGENT (captured
            // on no surface) -- not reconstructable from the live oracle buffers.
            <ul className="dx-agents" data-testid="agents-list">
              {Object.entries(ebpfCard.detected_per_surface).length === 0 &&
                ebpfCard.false_negatives.length === 0 && (
                  <li className="dx-empty">capture eBPF vide</li>
                )}
              {Object.entries(ebpfCard.detected_per_surface).map(([surface, n]) => (
                <li key={surface} className="dx-agent" data-testid={`ebpf-surface-${surface}`}>
                  <span className="dx-agent-id">{surface}</span>
                  <span className="dx-badge dx-badge-identifie" data-testid="agent-outcome">
                    DETECTE
                  </span>
                  <span className="dx-surfaces">{n} agent(s) vu(s) (capture noyau)</span>
                </li>
              ))}
              {ebpfCard.false_negatives.map((id) => (
                <li key={id} className="dx-agent" data-testid={`agent-${id}`}>
                  <span className="dx-agent-id">{id}</span>
                  <span className="dx-badge dx-badge-ghost" data-testid="agent-outcome">
                    GHOST
                  </span>
                  <span className="dx-surfaces">aucune surface (eBPF)</span>
                </li>
              ))}
              {/* An agent recorded with ZERO wire tokens (capture window missed
                  its traffic) yields an empty endpoint list: rendering it would
                  show a bare id row that says nothing -- skip it. */}
              {Object.entries(wireNamed)
                .filter(([, endpoints]) => endpoints.length > 0)
                .map(([agentId, endpoints]) => (
                <li
                  key={`wire-${agentId}`}
                  className="dx-agent dx-wire-agent"
                  data-testid={`wire-agent-${agentId}`}
                >
                  <span className="dx-agent-id">{agentId}</span>
                  <span className="dx-wire-endpoints">
                    {endpoints.map((ep) => {
                      const hostPort = ep.raw.replace(/^connect:/, "");
                      return (
                        <span key={ep.raw} className="dx-wire-endpoint">
                          <span className="dx-wire-named">
                            {ep.name !== null ? `${ep.name} (${hostPort})` : ep.raw}
                          </span>
                          {ep.undeclared && (
                            <span
                              className="dx-badge dx-badge-ghost dx-wire-undeclared"
                              data-testid="wire-undeclared"
                            >
                              host non declare
                            </span>
                          )}
                        </span>
                      );
                    })}
                  </span>
                </li>
              ))}
            </ul>
          ) : report !== null && shownAgents.length === 0 ? (
            <p className="dx-empty">Aucun agent observe.</p>
          ) : (
            <ul className="dx-agents" data-testid="agents-list">
              {shownAgents.map((a) => {
                const outcome = agentOutcome(a);
                return (
                  <li key={a.agent_id} className="dx-agent" data-testid={`agent-${a.agent_id}`}>
                    <span className="dx-agent-id">{a.agent_id}</span>
                    <span
                      className={`dx-badge dx-badge-${outcome === "DETECTE" ? "identifie" : "ghost"}`}
                      data-testid="agent-outcome"
                    >
                      {outcome}
                    </span>
                    <span className="dx-surfaces">
                      {detectedSurfaces(a).join(", ") || "aucune surface"}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
          {report !== null && (
            <p className="dx-scorecard" data-testid="scorecard">
              {report.scorecard.total_agents} agent(s),{" "}
              {report.scorecard.false_negatives.length} ghost(s)
              {showEbpf && ebpfCard !== null && (
                <> -- eBPF: {ebpfCard.false_negatives.length} ghost(s)</>
              )}
              {showEbpf && undeclaredHosts.length > 0 && (
                <span data-testid="dx-undeclared-hosts">
                  {" "}
                  -- {undeclaredHosts.length} host(s) non declare(s)
                </span>
              )}
            </p>
          )}
        </section>
      </div>
    </section>
  );
}
