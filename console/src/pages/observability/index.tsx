/**
 * Observability page (WS-C): a span-tree view of persisted runs.
 *
 * Lists the available traces (one per recording) and, on selection, renders the
 * run as a hierarchy of GenAI spans -- a root agent invocation with one
 * tool-execution span per action. Each tool span surfaces what the agent
 * actually DID: the action (tool), the target system + resource, the access
 * mode (read/write), the bound principal (I3) and whether the action was
 * approval-gated (I6). This is the legibility-first contract: a third party who
 * did not write the agent must understand, from the trace alone, what it asked.
 * The tree is a read-only projection of the audit recordings (I1), rendered
 * deterministically by the backend (I4). The request/response payload of each
 * tool lives in the cockpit network log (correlated by the action event id).
 */

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { getObservabilityTrace, listObservabilityTraces } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import type {
  ObservabilitySpan,
  ObservabilityTrace,
  ObservabilityTraceSummary,
} from "../../types/platform";
import "./observability.css";

/** Depth of a span = number of ancestors, walked through parent_span_id. */
function spanDepth(span: ObservabilitySpan, byId: Map<string, ObservabilitySpan>): number {
  let depth = 0;
  let parent = span.parent_span_id;
  while (parent) {
    const next = byId.get(parent);
    if (!next) break;
    depth += 1;
    parent = next.parent_span_id;
  }
  return depth;
}

function attr(span: ObservabilitySpan, key: string): string {
  const value = span.attributes[key];
  return value === undefined ? "" : String(value);
}

/** us when sub-millisecond, else ms -- a readable logical duration (I4). */
function humanDuration(nano: number): string {
  const us = nano / 1000;
  if (us < 1000) return `${Math.round(us)} us`;
  return `${(us / 1000).toFixed(us < 10000 ? 1 : 0)} ms`;
}

/** The decoded, display-ready shape of a span (what the agent did at this step). */
interface SpanView {
  span: ObservabilitySpan;
  depth: number;
  operation: string; // invoke_agent | execute_tool | ...
  /** Headline: the tool name for a tool call, else the agent name. */
  title: string;
  target: string;
  resource: string;
  mode: string; // read | write | ""
  principal: string;
  /** approval-gated? null = not a gated action, true/false = gated + outcome (I6). */
  approved: boolean | null;
  /** The intent the agent expressed for this step (tool arguments). */
  intent: string;
  /** The LLM decision text -- the "why" (empty for scripted/stub providers). */
  why: string;
}

function decode(span: ObservabilitySpan, depth: number): SpanView {
  const operation = attr(span, "gen_ai.operation.name");
  const tool = attr(span, "gen_ai.tool.name");
  const agent = attr(span, "gen_ai.agent.name") || attr(span, "gen_ai.agent.id");
  const mode = attr(span, "inspect_ia_agents.mode");
  const approvedRaw = span.attributes["inspect_ia_agents.approved"];
  // The approved attribute is present on gated (write) actions in the recording.
  const isGated = mode === "write" || approvedRaw !== undefined;
  return {
    span,
    depth,
    operation,
    title: tool || agent || span.name,
    target: attr(span, "inspect_ia_agents.target_system"),
    resource: attr(span, "inspect_ia_agents.resource"),
    mode,
    principal: attr(span, "inspect_ia_agents.principal"),
    approved: isGated ? Number(approvedRaw) === 1 : null,
    intent: attr(span, "gen_ai.tool.call.arguments"),
    why: attr(span, "inspect_ia_agents.decision"),
  };
}

function OperationTag({ operation }: { operation: string }): JSX.Element {
  const label =
    operation === "invoke_agent"
      ? "agent"
      : operation === "execute_tool"
        ? "tool"
        : operation || "span";
  return <span className={`obs-op obs-op-${operation || "node"}`}>{label}</span>;
}

export default function ObservabilityPage(): JSX.Element {
  const [traces, setTraces] = useState<ObservabilityTraceSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [trace, setTrace] = useState<ObservabilityTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");

  function toggleSpan(spanId: string): void {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(spanId)) next.delete(spanId);
      else next.add(spanId);
      return next;
    });
  }

  useEffect(() => {
    listObservabilityTraces()
      .then(setTraces)
      .catch((e: unknown) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (selected === null) return;
    setTrace(null);
    setOpen(new Set());
    getObservabilityTrace(selected)
      .then(setTrace)
      .catch((e: unknown) => setError(String(e)));
  }, [selected]);

  const byId = useMemo(() => {
    const map = new Map<string, ObservabilitySpan>();
    for (const s of trace?.spans ?? []) map.set(s.span_id, s);
    return map;
  }, [trace]);

  const views: SpanView[] = useMemo(
    () => (trace?.spans ?? []).map((s) => decode(s, spanDepth(s, byId))),
    [trace, byId],
  );

  const filteredTraces = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return traces;
    return traces.filter((t) =>
      [t.agent_id, t.recording_id, t.target_system, t.provider]
        .filter((v): v is string => Boolean(v))
        .some((v) => v.toLowerCase().includes(q)),
    );
  }, [traces, filter]);

  const selectedSummary = traces.find((t) => t.trace_id === selected) ?? null;

  const stats = useMemo(() => {
    const tools = views.filter((v) => v.operation === "execute_tool");
    const writes = tools.filter((v) => v.mode === "write");
    const unapproved = tools.filter((v) => v.approved === false);
    const targets = Array.from(
      new Set(tools.map((v) => v.target).filter((t): t is string => Boolean(t))),
    );
    return { actions: tools.length, writes: writes.length, unapproved: unapproved.length, targets };
  }, [views]);

  // The agent objective rides on the root invoke_agent span (the "why" context).
  const goal = useMemo(() => {
    const root = (trace?.spans ?? []).find(
      (s) => String(s.attributes["gen_ai.operation.name"]) === "invoke_agent",
    );
    return root ? String(root.attributes["inspect_ia_agents.goal"] ?? "") : "";
  }, [trace]);

  return (
    <section className="page observability-page">
      <div className="page-head">
        <h1>Observabilite -- traces</h1>
        <PageHelp topic="observability" />
      </div>
      <p className="obs-note">
        Arbre de spans de chaque run persiste (projection read-only de l'audit, I1). Chaque appel
        d'outil montre ce que l'agent a fait : l'action, le systeme cible, la ressource, le mode
        d'acces, le principal (I3) et l'etat d'approbation (I6).
      </p>
      {error && <p className="obs-error">{error}</p>}
      <div className="observability-layout">
        <div className="trace-panel">
          {traces.length > 0 && (
            <input
              type="search"
              className="obs-filter"
              placeholder="Filtrer (agent, systeme, recording)..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              data-testid="obs-filter"
              aria-label="Filtrer les traces"
            />
          )}
          <ul className="trace-list">
          {traces.length === 0 && (
            <li className="obs-empty" data-testid="obs-empty">
              Aucune trace pour l&apos;instant.{" "}
              <Link to="/cockpit" className="obs-empty-link" data-testid="obs-empty-cockpit-link">
                Lance un agent depuis le cockpit
              </Link>{" "}
              pour produire une trace.
            </li>
          )}
          {traces.length > 0 && filteredTraces.length === 0 && (
            <li className="obs-empty" data-testid="obs-no-match">
              Aucune trace ne correspond a "{filter}".
            </li>
          )}
          {filteredTraces.map((t) => (
            <li key={t.trace_id}>
              <button
                type="button"
                className={t.trace_id === selected ? "trace-row trace-row-active" : "trace-row"}
                onClick={() => setSelected(t.trace_id)}
              >
                <span className="trace-agent">{t.agent_id ?? t.recording_id}</span>
                <span className="trace-meta">
                  {t.target_system && (
                    <span className="obs-badge obs-badge-target">{t.target_system}</span>
                  )}
                  {t.provider && <span className="obs-badge obs-badge-provider">{t.provider}</span>}
                  <span className="obs-spancount">{t.span_count} span(s)</span>
                </span>
              </button>
            </li>
          ))}
          </ul>
        </div>

        <div className="span-tree">
          {trace === null ? (
            <p className="obs-hint">Selectionne une trace pour voir ce que l'agent a fait.</p>
          ) : (
            <>
              {selectedSummary && (
                <header className="obs-trace-head">
                  <span className="obs-trace-agent">
                    {selectedSummary.agent_id ?? selectedSummary.recording_id}
                  </span>
                  <code className="obs-trace-rec">{selectedSummary.recording_id}</code>
                  {goal && (
                    <p className="obs-goal" data-testid="obs-goal">
                      <span className="obs-k">objectif</span> {goal}
                    </p>
                  )}
                  <div className="obs-stats" data-testid="obs-stats">
                    <span className="obs-stat">
                      <strong>{stats.actions}</strong> action(s)
                    </span>
                    <span className="obs-stat">
                      <strong>{stats.writes}</strong> ecriture(s)
                    </span>
                    <span
                      className={
                        stats.unapproved > 0 ? "obs-stat obs-stat-alert" : "obs-stat"
                      }
                    >
                      <strong>{stats.unapproved}</strong> non approuvee(s)
                    </span>
                    {stats.targets.map((t) => (
                      <span key={t} className="obs-badge obs-badge-target">
                        {t}
                      </span>
                    ))}
                  </div>
                </header>
              )}
              <ol className="obs-spans">
                {views.map((v) => (
                  <li
                    key={v.span.span_id}
                    className="obs-span"
                    style={{ paddingLeft: `${v.depth * 1.4}rem` }}
                  >
                    <button
                      type="button"
                      className="obs-span-line"
                      aria-expanded={open.has(v.span.span_id)}
                      onClick={() => toggleSpan(v.span.span_id)}
                    >
                      <span className="obs-caret" aria-hidden="true">
                        {open.has(v.span.span_id) ? "v" : ">"}
                      </span>
                      <OperationTag operation={v.operation} />
                      <span className="obs-span-title">{v.title}</span>
                      {v.target && <span className="obs-badge obs-badge-target">{v.target}</span>}
                      {v.mode && (
                        <span className={`obs-badge obs-badge-mode obs-mode-${v.mode}`}>{v.mode}</span>
                      )}
                      {v.approved === true && (
                        <span className="obs-badge obs-badge-approved">approuve</span>
                      )}
                      {v.approved === false && (
                        <span className="obs-badge obs-badge-denied">non approuve</span>
                      )}
                      <span className="obs-span-dur">{humanDuration(v.span.duration_nano)}</span>
                    </button>
                    {(v.resource || v.principal || v.intent) && (
                      <div className="obs-span-sub">
                        {v.resource && (
                          <span className="obs-kv">
                            <span className="obs-k">ressource</span>
                            <code className="obs-v">{v.resource}</code>
                          </span>
                        )}
                        {v.intent && (
                          <span className="obs-kv">
                            <span className="obs-k">intention</span>
                            <code className="obs-v">{v.intent}</code>
                          </span>
                        )}
                        {v.principal && (
                          <span className="obs-kv">
                            <span className="obs-k">principal</span>
                            <code className="obs-v">{v.principal}</code>
                          </span>
                        )}
                      </div>
                    )}
                    {v.why && <p className="obs-why">{v.why}</p>}
                    {open.has(v.span.span_id) && (
                      <dl className="obs-attrs">
                        {Object.keys(v.span.attributes)
                          .sort()
                          .map((k) => (
                            <div className="obs-attr" key={k}>
                              <dt className="obs-attr-k">{k}</dt>
                              <dd className="obs-attr-v">{String(v.span.attributes[k])}</dd>
                            </div>
                          ))}
                      </dl>
                    )}
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
