/**
 * WirePanel -- the wire-overlay (mitmproxy) view of the Proxy page.
 *
 * Shows the NETWORK-level flows captured by the OPTIONAL mitmproxy Docker
 * overlay (the bytes on the wire of agent -> target traffic), as opposed to the
 * application-level ProxyTrace list on the main page. Read-only end to end (I1):
 * a flow describes an exchange that already happened; the panel only views and
 * clears the jettable buffer.
 *
 * Data path: a 1s DELTA poll (useDeltaFeed + getWireFlowsDelta) fetches only
 * the rows past the server cursor, and every filter clause (host/method/status/
 * run/free text) is pushed SERVER-SIDE as query params -- a filter change
 * restarts the feed (resetFeed) so the buffered rows always match the current
 * selection. The list itself is windowed (VirtualList) so a full client buffer
 * stays cheap to render, with tail-following while the follow toggle is on.
 *
 * When the overlay is not configured (INSPECT_IA_AGENTS_WIRE_PROXY unset) the panel
 * says so and how to enable it, instead of showing an empty list as a steady
 * state. The bodies are rendered in a plain read-only pane (no Monaco): the
 * request/response payloads are the point, and a plain pane renders under jsdom.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { clearWireFlows, controlWireOverlay, wireStreamUrl } from "../../api/client";
import { getWireFlowsDeltaTracked } from "./wireDeltaClient";
import ProxySelector from "../../components/ProxySelector";
import { VirtualList } from "../../components/VirtualList";
import type { WireFlow } from "../../types/platform";
import WireLayersView from "./WireLayersView";
import type { SourcePanelProps } from "./proxyMenu";
import { wireFlowToCurl } from "./curl";
import { decodeLlmFlow } from "./wireLlmDecode";
import { buildRunTimeline, isActionStep } from "./wireRunTimeline";
import { lineDiff } from "./diff";
import { byteLen, downloadFile, flowsToHar, toJsonl } from "./proxyExport";
import {
  distinctWireValues,
  filterWireFlows,
  type WireFlowFilter,
  type WireFlowLine,
  maxDuration,
  wireFailureCount,
  wireFlowToLine,
} from "./wireFlowModel";
import { useDeltaFeed, type DeltaEnvelope } from "./useDeltaFeed";
import WireFilterBar from "./WireFilterBar";
import InstanceSessionSummary from "./InstanceSessionSummary";
import WireExpertPanel from "./WireExpertPanel";
import WireInstancesPanel from "./WireInstancesPanel";
import WireStatsPanel from "./WireStatsPanel";
import { compileWireFilter } from "./wireFilter";
import { compileColorRules, type ColorTint } from "./wireColorRules";
import { fromAgentPcap, toAgentPcap, type AgentPcapImport } from "./agentpcap";
import { instanceId as flowInstanceId, sessionId as flowSessionId } from "./wireLayers";

const POLL_INTERVAL_MS = 1000;
/** Fixed row height of a virtualized wire row; MUST match the
 *  `.proxy-wire-vlist .proxy-wire-row` height in proxy.css (windowing math).
 *  Single-line packet-list rows; the latency strip overlays the row bottom. */
const ROW_HEIGHT_PX = 30;
/** Height of the windowed list viewport (VirtualList needs a fixed pixel
 *  height for its slice arithmetic). */
const LIST_HEIGHT_PX = 420;

const WIRE_TRUNCATION_MARKER = "...[truncated]"; // appended by recette/platform/proxy/wire.py _clamp_body when a body exceeds MAX_BODY_CHARS

/** One virtualized row: the flow's packet-list line plus its relative-latency
 *  width (precomputed so renderRow stays a pure presentation callback). */
interface WireRow extends WireFlowLine {
  /** Waterfall width in percent of the slowest buffered flow (layout only). */
  durationPct: number;
  /** First-matching coloring-rule tint, or null (no rule matched). */
  tint: ColorTint | null;
}

/** Render a body for display: pretty-print valid JSON when requested, else raw.
 *  Pure (no clock, no I/O); non-JSON falls back to the raw text. */
function renderBody(body: string, pretty: boolean): string {
  if (!pretty) return body;
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body; // not JSON -> raw
  }
}

export default function WirePanel({ onStatus, paused }: SourcePanelProps): JSX.Element {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [proxyUrl, setProxyUrl] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  // Second selection: the flow to compare the selected one against (a line diff
  // of their pretty-printed JSON -- e.g. a failing call vs a passing one).
  const [compareSeq, setCompareSeq] = useState<number | null>(null);
  const [nextStep, setNextStep] = useState<string | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  // Pretty-print toggle for the request/response body panes (display-only).
  const [pretty, setPretty] = useState(false);
  // Follow/tail toggle: when ON (and the page is not paused) the flow list
  // auto-pins to the latest flow after each poll. Display-only, no I4 impact.
  const [follow, setFollow] = useState(false);

  // Filter clauses live in the URL query string (deep-linkable + shareable):
  // host/method/status/q (free text) own their own keys, plus a read of the
  // page-owned `run`. The derived filter is the single source of truth -- there
  // is no duplicate local state for these keys. Every clause is pushed
  // SERVER-SIDE through the delta query params.
  const [params, setParams] = useSearchParams();
  const filter: WireFlowFilter = useMemo(
    () => ({
      host: params.get("host") ?? undefined,
      method: params.get("method") ?? undefined,
      status: params.get("status") ?? undefined,
      runId: params.get("run") ?? undefined,
      // Multi-session tracking narrowing (client-side): follow one instance
      // across the sessions it acted in, or pin one session.
      sessionId: params.get("session") ?? undefined,
      instanceId: params.get("instance") ?? undefined,
      df: params.get("df") ?? undefined,
      text: params.get("q") ?? undefined,
    }),
    [params],
  );

  // Set/delete ONE query key without clobbering the others (notably the
  // page-owned `source` and `run`): WirePanel only ever writes host/method/
  // status/q. `replace` keeps filtering out of the back/forward history.
  const setParam = useCallback(
    (key: string, value: string): void => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) {
            next.set(key, value);
          } else {
            next.delete(key);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  // Follow-agent-turn: both clauses land in ONE URL update — two successive
  // setParams in the same tick would race (the second reads a stale prev).
  const onFollowTurn = useCallback(
    (session: string | null, instance: string | null): void => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (session !== null) next.set("session", session);
          if (instance !== null) next.set("instance", instance);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  // The delta fetcher is rebuilt whenever a filter changes so it always reads
  // the CURRENT clause values (no stale closure). useDeltaFeed consumes the
  // fetcher through a ref, so a new identity does NOT tear down the poll
  // interval; the filter-change effect below restarts the feed instead.
  const fetcher = useCallback(
    (sinceSeq: number | null): Promise<DeltaEnvelope<WireFlow>> => {
      // The URL carries `status` as text (free input); the server takes an
      // exact integer status_code. A non-numeric value is not sent (the local
      // input still reflects it, the clause just matches nothing extra).
      const statusNum = filter.status && /^\d+$/.test(filter.status)
        ? Number(filter.status)
        : undefined;
      return getWireFlowsDeltaTracked({
        sinceSeq: sinceSeq ?? undefined,
        host: filter.host || undefined,
        method: filter.method || undefined,
        status: statusNum,
        runId: filter.runId || undefined,
        sessionId: filter.sessionId || undefined,
        instanceId: filter.instanceId || undefined,
        q: filter.text || undefined,
      }).then((res) => {
        // Side channel: every delta envelope carries enabled/proxy_url, so the
        // overlay state stays fresh WITHOUT a second status poll. The state
        // update runs in a promise callback (after commit, never during
        // render), so it is a safe place for this side effect.
        setEnabled(res.enabled);
        setProxyUrl(res.proxy_url);
        return { items: res.flows, last_seq: res.last_seq, reset: res.reset };
      });
    },
    [filter],
  );

  // Offline capture: an imported .agentpcap replaces the live feed as the
  // flow source until the operator returns to live (Wireshark open-file mode).
  const [imported, setImported] = useState<AgentPcapImport | null>(null);

  const { items: liveItems, error: feedError, refresh, resetFeed } = useDeltaFeed<WireFlow>(
    fetcher,
    {
      intervalMs: POLL_INTERVAL_MS,
      // An imported capture freezes the view: no point polling behind it.
      paused: (paused ?? false) || imported !== null,
    },
  );
  const items = imported !== null ? imported.flows : liveItems;

  // LIVE capture: the SSE stream is a data-light wake-up channel — each
  // `cursor` event triggers an immediate delta refresh (the poll remains the
  // fallback cadence). Runtimes without EventSource (jsdom) keep poll-only.
  useEffect(() => {
    if ((paused ?? false) || imported !== null) return undefined;
    if (typeof EventSource === "undefined") return undefined;
    const es = new EventSource(wireStreamUrl());
    const onCursor = (): void => void refresh();
    es.addEventListener("cursor", onCursor);
    return (): void => {
      es.removeEventListener("cursor", onCursor);
      es.close();
    };
  }, [paused, imported, refresh]);

  // Server-side filters: any clause change invalidates the cursor AND the
  // buffered rows (they belong to the previous selection), so the feed is
  // restarted. Skipped on mount -- the hook already fetches full there.
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    resetFeed();
  }, [filter.host, filter.method, filter.status, filter.runId,
      filter.sessionId, filter.instanceId, filter.text, resetFeed]);

  // Headline status for the source menu. Gated on the first envelope so the
  // badge never flashes "off" before the backend has answered once.
  useEffect(() => {
    if (enabled === null) {
      return;
    }
    onStatus?.({
      count: items.length,
      failed: wireFailureCount(items),
      disabled: !enabled,
    });
  }, [items, enabled, onStatus]);

  // Follow UX: while the user is scrolled away from the tail, count the flows
  // that landed since they left; a badge lets them jump back to live tailing
  // by bumping the VirtualList scroll-to-tail signal.
  const [awayFromTail, setAwayFromTail] = useState(false);
  const [tailSignal, setTailSignal] = useState(0);
  // Latest-value ref so the (stable) scroll callback reads the current count.
  const itemCountRef = useRef(0);
  itemCountRef.current = items.length;
  const awayBaselineRef = useRef(0);
  const onScrollAwayFromTail = useCallback((away: boolean): void => {
    if (away) {
      awayBaselineRef.current = itemCountRef.current;
    }
    setAwayFromTail(away);
  }, []);
  const newSinceAway = awayFromTail ? Math.max(0, items.length - awayBaselineRef.current) : 0;
  const onResumeFollow = useCallback((): void => {
    setTailSignal((s) => s + 1);
    setAwayFromTail(false);
  }, []);

  const onClear = useCallback(async (): Promise<void> => {
    try {
      await clearWireFlows();
      setSelectedSeq(null);
      setCompareSeq(null);
      setActionError(null);
      resetFeed();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }, [resetFeed]);

  const onToggleOverlay = useCallback(async (): Promise<void> => {
    setBusy(true);
    try {
      const res = await controlWireOverlay(enabled === true ? "down" : "up");
      setNextStep(res.next_step);
      setActionError(null);
      await refresh();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [enabled, refresh]);

  // Restart the overlay in one click: stop then start (the API exposes up/down
  // only, so a restart is down-then-up). Fail-safe: a failed 'down' still tries
  // 'up' is NOT assumed -- a down error aborts and is surfaced, never a silent
  // half-restart claimed as done.
  const onRestartOverlay = useCallback(async (): Promise<void> => {
    setBusy(true);
    try {
      await controlWireOverlay("down");
      const res = await controlWireOverlay("up");
      setNextStep(res.next_step);
      setActionError(null);
      await refresh();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  // The select options derive from the CURRENTLY buffered (already filtered)
  // rows: once a clause is set the other options narrow with it. Accepted
  // trade-off of server-side filtering -- clearing the clause widens again.
  const hosts = useMemo(() => distinctWireValues(items, "host"), [items]);
  const methods = useMemo(() => distinctWireValues(items, "method"), [items]);
  const runIds = useMemo(() => distinctWireValues(items, "run_id"), [items]);
  // Client-side narrowing: the tracking backstop (server already filters session/
  // instance) THEN the Wireshark display-filter predicate over the dissected
  // fields. Compiling once yields the predicate + a parse error to surface.
  const dfCompiled = useMemo(() => compileWireFilter(filter.df ?? ""), [filter.df]);
  const visible = useMemo(
    () =>
      filterWireFlows(items, {
        sessionId: filter.sessionId,
        instanceId: filter.instanceId,
      }).filter(dfCompiled.predicate),
    [items, filter.sessionId, filter.instanceId, dfCompiled],
  );
  // Waterfall scale: the largest latency among the buffered flows. duration_ms
  // is OPS metadata on the view only, never a judge/decision/replay input (I4).
  const maxDur = useMemo(() => maxDuration(visible), [visible]);
  // Coloring rules (Wireshark profiles): URL-owned so a colored view is
  // deep-linkable; first matching rule tints the row (wireColorRules.ts).
  const colorsSrc = params.get("colors") ?? "";
  const colorRules = useMemo(() => compileColorRules(colorsSrc), [colorsSrc]);
  const rows: WireRow[] = useMemo(
    () =>
      visible.map((f) => ({
        ...wireFlowToLine(f),
        // Width % is layout (relative latency), not a hardcoded color.
        durationPct: maxDur > 0 ? Math.round(((f.duration_ms ?? 0) / maxDur) * 100) : 0,
        tint: colorRules.tintFor(f),
      })),
    [visible, maxDur, colorRules],
  );
  const fails = useMemo(() => wireFailureCount(visible), [visible]);
  const selected = useMemo(
    () => visible.find((f) => f.seq === selectedSeq) ?? null,
    [visible, selectedSeq],
  );
  // Semantic decode of the selected flow when it targets an LLM API: lifts the
  // raw HTTP body into model/messages/tools/answer. Pure + display-only (I4):
  // a deterministic function of the flow bytes, never a judge/decision input.
  // Null for a non-LLM flow -> the raw body pane stays the source of truth.
  const llm = useMemo(() => (selected !== null ? decodeLlmFlow(selected) : null), [selected]);
  // Decision timeline of the followed scope. Two ways to scope a "turn":
  // a run clause (cockpit deep-link) or a followed agent turn (session +
  // instance, the Follow-TCP-Stream equivalent). Either way the buffered flows
  // are exactly that scope's flows, so ordering by capture sequence
  // reconstructs the reasoning -> effect story.
  const followingTurn = filter.sessionId !== undefined && filter.instanceId !== undefined;
  const timeline = useMemo(
    () => (filter.runId !== undefined || followingTurn ? buildRunTimeline(visible) : []),
    [filter.runId, followingTurn, visible],
  );
  const compareFlow = useMemo(
    () => visible.find((f) => f.seq === compareSeq) ?? null,
    [visible, compareSeq],
  );
  // Side-by-side line diff of the two flows' pretty-printed JSON. Pure (I4):
  // a deterministic function of the two selected flows (no clock, no I/O).
  const diffRows = useMemo(
    () =>
      selected !== null && compareFlow !== null
        ? lineDiff(
            JSON.stringify(selected, null, 2),
            JSON.stringify(compareFlow, null, 2),
          )
        : null,
    [selected, compareFlow],
  );

  const onExportJsonl = useCallback((): void => {
    // Forensic snapshot of the CURRENTLY buffered flows (bounded by the ring).
    downloadFile(`${toJsonl(items)}\n`, "wire-flows.jsonl", "application/x-ndjson");
  }, [items]);

  const onExportHar = useCallback((): void => {
    downloadFile(flowsToHar(items), "wire-flows.har", "application/json");
  }, [items]);

  // Portable capture: export the buffered flows as a verifiable .agentpcap;
  // import one to inspect a shared capture OFFLINE (agentpcap.ts).
  const pcapInputRef = useRef<HTMLInputElement | null>(null);
  const onExportPcap = useCallback((): void => {
    downloadFile(toAgentPcap(items), "capture.agentpcap.json", "application/json");
  }, [items]);
  const onImportPcap = useCallback((e: ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (file === undefined) return;
    // FileReader (not File.text()): available in every runtime incl. jsdom.
    const reader = new FileReader();
    reader.onload = (): void => setImported(fromAgentPcap(String(reader.result ?? "")));
    reader.readAsText(file);
    // Allow re-importing the same filename later.
    e.target.value = "";
  }, []);

  const itemKey = useCallback((r: WireRow): number => r.seq, []);
  const renderRow = useCallback(
    (r: WireRow): ReactNode => (
      <div className="proxy-wire-row" data-parity={r.seq % 2 === 0 ? "even" : "odd"}>
        <button
          type="button"
          className="proxy-list-item wire-prow"
          data-active={r.seq === selectedSeq}
          data-outcome={r.outcome}
          data-tint={r.tint ?? undefined}
          onClick={() => setSelectedSeq(r.seq)}
        >
          <span className="wire-col wire-col-seq">{r.seq}</span>
          <span className="wire-col wire-col-status" data-outcome={r.outcome}>
            {r.status_code}
          </span>
          <span className="wire-col wire-col-method">{r.method}</span>
          <span className="wire-col wire-col-host" title={r.host}>
            {r.host}
          </span>
          <span className="wire-col wire-col-path" title={r.path}>
            {r.path}
          </span>
          <span className="wire-col wire-col-inst" title={r.instance ?? undefined}>
            {r.instance ?? ""}
          </span>
          {/* Waterfall strip: latency relative to the slowest shown flow. */}
          <span className="proxy-wire-bar" style={{ width: `${r.durationPct}%` }} />
        </button>
        <button
          type="button"
          className="proxy-export proxy-wire-compare-btn"
          data-testid={`wire-compare-${r.seq}`}
          data-active={r.seq === compareSeq}
          onClick={() => setCompareSeq(r.seq)}
          title={`comparer le flux #${r.seq} au flux selectionne`}
        >
          comparer
        </button>
      </div>
    ),
    [selectedSeq, compareSeq],
  );

  const shownError = actionError ?? feedError;

  return (
    <section className="proxy-wire" data-testid="wire-panel">
      <header className="proxy-header">
        <ProxySelector />
        <span className="proxy-summary">
          {visible.length} flux, {fails} echec(s)
        </span>
        {enabled === true && proxyUrl !== null && (
          <span className="proxy-wire-proxy" data-testid="wire-proxy-url">
            proxy: <code>{proxyUrl}</code>
          </span>
        )}
        <button
          type="button"
          className="proxy-clear"
          data-testid="wire-overlay-toggle"
          disabled={busy}
          onClick={() => void onToggleOverlay()}
        >
          {enabled === true ? "Arreter le reseau (wire)" : "Demarrer le reseau (wire)"}
        </button>
        <button
          type="button"
          className="proxy-clear"
          data-testid="wire-overlay-restart"
          disabled={busy}
          onClick={() => void onRestartOverlay()}
        >
          Redemarrer (wire)
        </button>
        <button
          type="button"
          className="proxy-mode-btn"
          data-testid="wire-follow"
          aria-pressed={follow}
          onClick={() => setFollow((f) => !f)}
        >
          {follow ? "Suivi ON" : "Suivi"}
        </button>
        <button type="button" className="proxy-export" onClick={onExportJsonl}>
          Export JSONL
        </button>
        <button
          type="button"
          className="proxy-export"
          data-testid="wire-export-har"
          onClick={onExportHar}
        >
          Export HAR
        </button>
        <button
          type="button"
          className="proxy-export"
          data-testid="wire-export-pcap"
          onClick={onExportPcap}
        >
          Export .agentpcap
        </button>
        <button
          type="button"
          className="proxy-export"
          data-testid="wire-import-pcap-btn"
          onClick={() => pcapInputRef.current?.click()}
        >
          Importer .agentpcap
        </button>
        <input
          ref={pcapInputRef}
          type="file"
          accept=".json,.agentpcap"
          style={{ display: "none" }}
          data-testid="wire-import-pcap"
          onChange={onImportPcap}
        />
        <button type="button" className="proxy-clear" onClick={() => void onClear()}>
          Vider le tampon
        </button>
      </header>

      <WireFilterBar
        filter={filter}
        setParam={setParam}
        hosts={hosts}
        methods={methods}
        runIds={runIds}
        dfError={dfCompiled.ok ? null : dfCompiled.error}
        colors={colorsSrc}
        colorsError={
          colorRules.errors.length > 0
            ? colorRules.errors.map((e) => `regle ${e.index + 1}: ${e.error}`).join(" ; ")
            : null
        }
      />

      {nextStep !== null && (
        <p className="proxy-banner" role="status" data-testid="wire-next-step">
          {nextStep}
        </p>
      )}

      {/* Offline mode: an imported capture replaces the live feed; the integrity
          verdict (chain recomputation) is always shown to the auditor. */}
      {imported !== null && (
        <p className="proxy-banner" role="status" data-testid="wire-imported">
          Capture importee ({imported.flows.length} flux) — integrite{" "}
          {imported.verified ? "verifiee" : "INVALIDE"}
          {imported.error !== null ? ` : ${imported.error}` : ""}.{" "}
          <button
            type="button"
            className="proxy-mode-btn"
            data-testid="wire-import-clear"
            onClick={() => setImported(null)}
          >
            revenir au direct
          </button>
        </p>
      )}

      {/* Orchestration roster: with no instance pinned, list every instance in
          the capture and deep-link into one (instance -> its wire flows). Once
          an instance is pinned, the cross-session strip below takes over. */}
      {filter.instanceId === undefined && (
        <WireInstancesPanel flows={visible} onPick={(iid) => setParam("instance", iid)} />
      )}

      <InstanceSessionSummary
        instanceId={filter.instanceId}
        flows={visible}
        activeSession={filter.sessionId}
        onPickSession={(sid) => setParam("session", sid)}
      />

      <WireStatsPanel flows={visible} />

      {/* Expert info (defensive conformance signals): each signal opens the
          flow it is anchored on, like Wireshark's expert dialog. */}
      <WireExpertPanel flows={visible} onPick={setSelectedSeq} />

      {/* Flows can arrive via the transport-route registry even when
          INSPECT_IA_AGENTS_WIRE_PROXY is unset (enabled=false); yield the
          how-to-enable banner to actual data. */}
      {/* Off AND empty AND no start action in flight: a fresh disabled overlay.
          Once the operator clicked "Demarrer" (busy) or the API returned a
          next-step note, the overlay is (being) enabled -- the "desactivee"
          banner would be false, so it yields to the next-step note above. */}
      {enabled === false && items.length === 0 && !busy && nextStep === null && (
        <p className="proxy-banner" role="status" data-testid="wire-disabled">
          Surcouche wire desactivee (aucun flux capture). Le plus simple:{" "}
          <code>./recette.sh all up</code> demarre la plateforme avec l'overlay
          actif d'un coup. Sinon, cliquer <strong>Demarrer le reseau (wire)</strong>{" "}
          ci-dessus, PUIS choisir la route <strong>Wire (mitmproxy)</strong> dans
          le selecteur -- c'est cette etape qui active la capture (effet immediat,
          runs suivants). Pour le HTTPS des systemes reels, faire aussi confiance
          au CA (<code>./recette.sh wire ca</code> {"->"}{" "}
          <code>INSPECT_IA_AGENTS_WIRE_CA</code>) puis{" "}
          <code>./recette.sh api restart</code>.
        </p>
      )}
      {shownError !== null && <p className="proxy-error">{shownError}</p>}

      {/* Decision timeline of the selected run: the reasoning -> effect story in
          capture order, action steps (tool decided / mutating call) highlighted,
          each clickable to open its full flow -- so an undesired action is found
          at its exact step. Shown when a run clause OR a followed agent turn
          (session + instance) scopes the flows. */}
      {(filter.runId !== undefined || followingTurn) && timeline.length > 0 && (
        <div className="proxy-wire-timeline" data-testid="wire-run-timeline">
          <div className="proxy-wire-timeline-head">
            {filter.runId !== undefined
              ? `Timeline decision -- run ${filter.runId.slice(0, 12)} (${timeline.length} etapes)`
              : `Tour d'agent -- ${filter.instanceId ?? ""} / session ${filter.sessionId ?? ""} (${timeline.length} etapes)`}
          </div>
          <ol className="proxy-wire-timeline-list">
            {timeline.map((s) => (
              <li
                key={s.seq}
                className="proxy-wire-timeline-step"
                data-kind={s.kind}
                data-action={isActionStep(s)}
                data-testid={`wire-step-${s.seq}`}
              >
                <button
                  type="button"
                  className="proxy-wire-step-btn"
                  onClick={() => setSelectedSeq(s.seq)}
                >
                  <span className="proxy-wire-step-seq">#{s.seq}</span>
                  {s.kind === "decision" ? (
                    <span className="proxy-wire-step-body">
                      <span className="proxy-wire-step-tag">
                        reflexion{s.model !== null ? ` (${s.model})` : ""}
                      </span>
                      {s.answer !== null && (
                        <span className="proxy-wire-step-text">{s.answer}</span>
                      )}
                      {s.toolCalls.length > 0 && (
                        <span
                          className="proxy-wire-step-action"
                          data-testid={`wire-step-decides-${s.seq}`}
                        >
                          decide: {s.toolCalls.join(", ")}
                        </span>
                      )}
                    </span>
                  ) : (
                    <span className="proxy-wire-step-body">
                      <span className="proxy-wire-step-tag">effet</span>
                      <span className="proxy-wire-step-text">
                        {s.method} {s.host}
                        {s.path} {"->"} {s.status}
                      </span>
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="proxy-grid">
        {/* The wrapper keeps the list role/label the page contract asserts on;
            the rows themselves are windowed by VirtualList. */}
        <div
          className="proxy-list proxy-vlist proxy-wire-vlist"
          role="list"
          aria-label="wire flows"
        >
          <div className="wire-list-head" aria-hidden="true">
            <span className="wire-col wire-col-seq">No</span>
            <span className="wire-col wire-col-status">Statut</span>
            <span className="wire-col wire-col-method">Methode</span>
            <span className="wire-col wire-col-host">Hote</span>
            <span className="wire-col wire-col-path">Chemin</span>
            <span className="wire-col wire-col-inst">Instance</span>
            <span className="wire-col wire-col-cmp" />
          </div>
          {newSinceAway > 0 && (
            <button
              type="button"
              className="proxy-new-badge"
              data-testid="wire-new-flows"
              onClick={onResumeFollow}
            >
              {newSinceAway} nouveaux flux -- reprendre le suivi
            </button>
          )}
          {rows.length === 0 ? (
            <div className="proxy-empty">aucun flux</div>
          ) : (
            <VirtualList<WireRow>
              items={rows}
              rowHeight={ROW_HEIGHT_PX}
              height={LIST_HEIGHT_PX}
              renderRow={renderRow}
              itemKey={itemKey}
              followTail={follow && !paused}
              onScrollAwayFromTail={onScrollAwayFromTail}
              scrollToTailSignal={tailSignal}
              testId="wire-flow-vlist"
            />
          )}
        </div>
        <div className="proxy-viewer proxy-wire-detail">
          {selected === null ? (
            <p className="proxy-viewer-msg">selectionner un flux a gauche</p>
          ) : (
            <dl className="proxy-wire-kv" data-testid="wire-detail">
              {llm !== null && (
                <>
                  <dt>LLM</dt>
                  <dd>
                    <div className="proxy-wire-llm" data-testid="wire-llm-decode">
                      <div className="proxy-wire-llm-head">
                        {llm.provider}
                        {llm.model !== null ? " (" + llm.model + ")" : ""}
                      </div>
                      {llm.messages.length > 0 && (
                        <ol className="proxy-wire-llm-msgs">
                          {llm.messages.map((m, i) => (
                            <li key={i}>
                              <span className="proxy-wire-llm-role">{m.role}</span>
                              <span className="proxy-wire-llm-text">{m.text}</span>
                            </li>
                          ))}
                        </ol>
                      )}
                      {llm.tools.length > 0 && (
                        <div data-testid="wire-llm-tools">
                          tools offerts: {llm.tools.join(", ")}
                        </div>
                      )}
                      {llm.toolCalls.length > 0 && (
                        <div data-testid="wire-llm-toolcalls">
                          tools appeles: {llm.toolCalls.join(", ")}
                        </div>
                      )}
                      {llm.responseText !== null && (
                        <div className="proxy-wire-llm-answer" data-testid="wire-llm-answer">
                          reponse: {llm.responseText}
                        </div>
                      )}
                      {(llm.usage !== null || llm.stop !== null) && (
                        <div className="proxy-wire-llm-meta">
                          {llm.usage !== null && (
                            <span>
                              tokens: {llm.usage.input ?? "?"} {"->"} {llm.usage.output ?? "?"}
                            </span>
                          )}
                          {llm.stop !== null && <span> stop: {llm.stop}</span>}
                        </div>
                      )}
                    </div>
                  </dd>
                </>
              )}
              <dt>reseau</dt>
              <dd>
                <WireLayersView flow={selected} />
              </dd>
              {/* Follow-agent-turn (the Follow-TCP-Stream equivalent): scope the
                  capture to this flow's session + instance in one click; the
                  clauses land in the URL, so the followed turn is deep-linkable. */}
              {(flowSessionId(selected) !== null || flowInstanceId(selected) !== null) && (
                <>
                  <dt>suivre</dt>
                  <dd>
                    <button
                      type="button"
                      className="proxy-export"
                      data-testid="wire-follow-turn"
                      onClick={() => onFollowTurn(flowSessionId(selected), flowInstanceId(selected))}
                    >
                      Suivre ce tour d'agent
                    </button>
                  </dd>
                </>
              )}
              <dt>replay</dt>
              <dd>
                <button
                  type="button"
                  className="proxy-export"
                  data-testid="wire-copy-curl"
                  onClick={() => void navigator.clipboard?.writeText(wireFlowToCurl(selected))}
                >
                  Copy curl
                </button>
              </dd>
              <dt>requete</dt>
              <dd>
                {selected.method} {selected.scheme}://{selected.host}:{selected.port}
                {selected.path}
              </dd>
              <dt>statut</dt>
              <dd>{selected.status_code}</dd>
              {selected.duration_ms != null && (
                <>
                  <dt>latence</dt>
                  <dd data-testid="wire-duration">{selected.duration_ms} ms</dd>
                </>
              )}
              <dt>content-type</dt>
              <dd>{selected.content_type || "-"}</dd>
              <dt>affichage</dt>
              <dd>
                <button
                  type="button"
                  className="proxy-export"
                  data-testid="wire-pretty-toggle"
                  onClick={() => setPretty((p) => !p)}
                >
                  {pretty ? "Brut" : "Pretty"}
                </button>
              </dd>
              <dt>
                corps requete
                <span className="proxy-wire-size">
                  {" "}
                  {byteLen(selected.request_body)} o
                  {selected.request_body.endsWith(WIRE_TRUNCATION_MARKER) && (
                    <span data-testid="wire-req-truncated"> (tronque)</span>
                  )}
                </span>
              </dt>
              <dd>
                <pre className="proxy-wire-body">
                  {renderBody(selected.request_body, pretty) || "(vide)"}
                </pre>
              </dd>
              <dt>
                corps reponse
                <span className="proxy-wire-size">
                  {" "}
                  {byteLen(selected.response_body)} o
                  {selected.response_body.endsWith(WIRE_TRUNCATION_MARKER) && (
                    <span data-testid="wire-resp-truncated"> (tronque)</span>
                  )}
                </span>
              </dt>
              <dd>
                <pre className="proxy-wire-body">
                  {renderBody(selected.response_body, pretty) || "(vide)"}
                </pre>
              </dd>
            </dl>
          )}
        </div>
      </div>

      {diffRows !== null && selected !== null && compareFlow !== null && (
        <div className="proxy-wire-diff" data-testid="wire-diff">
          <div className="proxy-wire-diff-head">
            <span>
              diff: #{selected.seq} vs #{compareFlow.seq}
            </span>
            <button
              type="button"
              className="proxy-export"
              data-testid="wire-diff-clear"
              onClick={() => setCompareSeq(null)}
            >
              X
            </button>
          </div>
          <table className="proxy-wire-diff-table">
            <tbody>
              {diffRows.map((row, i) => (
                <tr key={i} className="proxy-wire-diff-row" data-kind={row.kind}>
                  <td className="proxy-wire-diff-cell" data-side="left">
                    {row.left}
                  </td>
                  <td className="proxy-wire-diff-cell" data-side="right">
                    {row.right}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
