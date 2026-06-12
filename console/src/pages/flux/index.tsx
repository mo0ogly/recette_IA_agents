/**
 * Flux page -- live analysis window over the agents' audit flux.
 *
 * Left: the reusable LogConsole tailing the audit log (bounded useAuditTail);
 * clicking a line selects the event. Right: the Monaco FluxAnalyzer showing
 * either the selected event (pretty JSON) or the whole visible window as
 * JSONL ("stream" mode). Read-only end to end: the audit log is immutable
 * (I1) and this page never writes.
 *
 * Deep links (mirrors the audit page ?event_id= pattern):
 * - ?agent_id=X pre-applies the per-agent filter;
 * - ?seq=N pre-selects an event once it is present in the tail buffer.
 */

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { auditExportUrl, listAgents } from "../../api/client";
import { FluxAnalyzer, type FluxAnalyzerMode } from "../../components/FluxAnalyzer";
import { auditEventToLogLine, LogConsole } from "../../components/LogConsole";
import { useAuditTail } from "../../hooks/useAuditTail";
import type { AgentConfig } from "../../types/platform";
import "./flux.css";

export default function FluxPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const agentFilter = searchParams.get("agent_id") ?? "";
  const seqParam = searchParams.get("seq");

  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(
    seqParam !== null && /^\d+$/.test(seqParam) ? Number(seqParam) : null,
  );
  const [mode, setMode] = useState<FluxAnalyzerMode>("event");

  const audit = useAuditTail({ agentId: agentFilter === "" ? undefined : agentFilter });

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
      setSelectedSeq(null);
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
      setSelectedSeq(seq);
      setMode("event");
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("seq", String(seq));
        return next;
      });
    },
    [setSearchParams],
  );

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
        </span>
        <a className="flux-export" href={auditExportUrl()} download>
          Export JSONL
        </a>
      </header>
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
        <FluxAnalyzer events={audit.events} selectedSeq={selectedSeq} mode={mode} />
      </div>
    </section>
  );
}
