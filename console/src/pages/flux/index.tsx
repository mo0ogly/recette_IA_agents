/**
 * Flux page -- live analysis window over the agents' audit flux.
 *
 * Left: the reusable LogConsole tailing the audit log (bounded useAuditTail);
 * clicking a line selects the event. Right: the Monaco FluxAnalyzer showing
 * either the selected event (pretty JSON) or the whole visible window as
 * JSONL ("stream" mode). Read-only end to end: the audit log is immutable
 * (I1) and this page never writes.
 *
 * Deep links: ?agent_id=X pre-applies the per-agent filter; ?seq=N selects an
 * event. The URL is the single source of truth for both (selection survives
 * back/forward navigation). The analyzer mode is deliberately ephemeral UI
 * state and is NOT reflected in the URL.
 *
 * Export: client-side JSONL of the VISIBLE window only (bounded by the tail
 * buffer). The full-log server export exists for SIEM tooling; an unbounded
 * download link does not belong in a live viewer.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { listAgents } from "../../api/client";
import {
  FluxAnalyzer,
  fluxAnalyzerContent,
  type FluxAnalyzerMode,
} from "../../components/FluxAnalyzer";
import { distinctPayloadValues, type FluxFilter } from "../../components/fluxModel";
import { auditEventToLogLine, LogConsole } from "../../components/LogConsole";
import { useAuditTail } from "../../hooks/useAuditTail";
import type { AgentConfig } from "../../types/platform";
import "./flux.css";

export default function FluxPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const agentFilter = searchParams.get("agent_id") ?? "";
  const seqParam = searchParams.get("seq");
  // Derived, not duplicated into state: back/forward keeps URL and view in sync.
  const selectedSeq = seqParam !== null && /^\d+$/.test(seqParam) ? Number(seqParam) : null;

  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [mode, setMode] = useState<FluxAnalyzerMode>("event");

  // Stream-mode governance filter (ephemeral UI state, not reflected in the URL).
  const [actionType, setActionType] = useState("");
  const [targetSystem, setTargetSystem] = useState("");
  const [minRisk, setMinRisk] = useState("");
  // Diff-mode comparands (left A / right B), chosen from the visible window.
  const [diffA, setDiffA] = useState<number | null>(null);
  const [diffB, setDiffB] = useState<number | null>(null);

  const audit = useAuditTail({ agentId: agentFilter === "" ? undefined : agentFilter });

  const filter: FluxFilter = useMemo(() => {
    const f: FluxFilter = {};
    if (actionType !== "") {
      f.actionType = actionType;
    }
    if (targetSystem !== "") {
      f.targetSystem = targetSystem;
    }
    const parsed = Number(minRisk);
    if (minRisk !== "" && Number.isFinite(parsed)) {
      f.minRisk = parsed;
    }
    return f;
  }, [actionType, targetSystem, minRisk]);

  const actionTypes = useMemo(
    () => distinctPayloadValues(audit.events, "action_type"),
    [audit.events],
  );
  const targetSystems = useMemo(
    () => distinctPayloadValues(audit.events, "target_system"),
    [audit.events],
  );
  const seqs = useMemo(() => audit.events.map((e) => e.seq), [audit.events]);

  useEffect(() => {
    listAgents()
      .then(setAgents)
      .catch((err: unknown) => {
        setAgentsError(err instanceof Error ? err.message : String(err));
      });
  }, []);

  const onAgentChange = useCallback(
    (value: string) => {
      // Filter change resets the tail (hook semantics); drop the selection too.
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value === "") {
          next.delete("agent_id");
        } else {
          next.set("agent_id", value);
        }
        next.delete("seq");
        return next;
      });
    },
    [setSearchParams],
  );

  const onLineClick = useCallback(
    (seq: number) => {
      setMode("event");
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("seq", String(seq));
        return next;
      });
    },
    [setSearchParams],
  );

  const exportWindow = useCallback(() => {
    // Bounded by construction: only the visible tail buffer is serialized.
    const jsonl = fluxAnalyzerContent(audit.events, null, "stream");
    const blob = new Blob([`${jsonl}\n`], { type: "application/x-ndjson" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "flux-window.jsonl";
    anchor.click();
    URL.revokeObjectURL(url);
  }, [audit.events]);

  // Keep the controlled select coherent while agents are still loading: a
  // value without a matching option would silently snap to the first option.
  const agentKnown = agents.some((a) => a.id === agentFilter);

  return (
    <section className="flux-page">
      <header className="flux-header">
        <h1>Flux</h1>
        <label className="flux-agent-label">
          Agent
          <select
            className="flux-agent-select"
            value={agentFilter}
            onChange={(e) => onAgentChange(e.target.value)}
          >
            <option value="">all agents</option>
            {agentFilter !== "" && !agentKnown && (
              <option value={agentFilter}>{agentFilter}</option>
            )}
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.id}
              </option>
            ))}
          </select>
        </label>
        <span className="flux-mode" role="group" aria-label="analyzer mode">
          <button
            type="button"
            className="flux-mode-btn"
            data-active={mode === "event"}
            onClick={() => setMode("event")}
          >
            event
          </button>
          <button
            type="button"
            className="flux-mode-btn"
            data-active={mode === "stream"}
            onClick={() => setMode("stream")}
          >
            stream
          </button>
          <button
            type="button"
            className="flux-mode-btn"
            data-active={mode === "diff"}
            onClick={() => setMode("diff")}
          >
            diff
          </button>
        </span>
        <button type="button" className="flux-export" onClick={exportWindow}>
          Export window (JSONL)
        </button>
      </header>
      {mode === "stream" && (
        <div className="flux-filter" role="group" aria-label="stream filter">
          <label className="flux-filter-label">
            action_type
            <select
              className="flux-filter-input"
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
            >
              <option value="">any</option>
              {actionTypes.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label className="flux-filter-label">
            target_system
            <select
              className="flux-filter-input"
              value={targetSystem}
              onChange={(e) => setTargetSystem(e.target.value)}
            >
              <option value="">any</option>
              {targetSystems.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="flux-filter-label">
            min risk
            <input
              className="flux-filter-input"
              type="number"
              min={0}
              value={minRisk}
              onChange={(e) => setMinRisk(e.target.value)}
              placeholder="0"
            />
          </label>
        </div>
      )}
      {mode === "diff" && (
        <div className="flux-filter" role="group" aria-label="diff selection">
          <label className="flux-filter-label">
            A (original)
            <select
              className="flux-filter-input"
              value={diffA ?? ""}
              onChange={(e) => setDiffA(e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">pick</option>
              {seqs.map((s) => (
                <option key={s} value={s}>
                  seq {s}
                </option>
              ))}
            </select>
          </label>
          <label className="flux-filter-label">
            B (modified)
            <select
              className="flux-filter-input"
              value={diffB ?? ""}
              onChange={(e) => setDiffB(e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">pick</option>
              {seqs.map((s) => (
                <option key={s} value={s}>
                  seq {s}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {agentsError !== null && <p className="flux-error">{agentsError}</p>}
      <div className="flux-grid">
        <LogConsole
          title="Agent flux (live)"
          lines={audit.events.map(auditEventToLogLine)}
          onClear={audit.clear}
          stalled={audit.stalled}
          droppedCount={audit.droppedCount}
          onLineClick={onLineClick}
          selectedSeq={selectedSeq}
        />
        <FluxAnalyzer
          events={audit.events}
          selectedSeq={selectedSeq}
          mode={mode}
          filter={filter}
          diffSeqs={[diffA, diffB]}
        />
      </div>
    </section>
  );
}
