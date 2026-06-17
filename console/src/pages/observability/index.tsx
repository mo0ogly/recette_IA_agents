/**
 * Observability page (WS-C): a span-tree view of persisted runs.
 *
 * Lists the available traces (one per recording) and, on selection, renders
 * the run as a hierarchy of GenAI spans -- a root agent invocation with one
 * tool-execution span per action -- with logical durations. The tree is a
 * read-only projection of the audit recordings (I1); the backend renders it
 * deterministically (I4). The exchange request/response of each tool lives in
 * the cockpit network log (correlated by the action event id).
 */

import { useEffect, useMemo, useState } from "react";

import { getObservabilityTrace, listObservabilityTraces } from "../../api/client";
import type {
  ObservabilitySpan,
  ObservabilityTrace,
  ObservabilityTraceSummary,
} from "../../types/platform";

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

export default function ObservabilityPage(): JSX.Element {
  const [traces, setTraces] = useState<ObservabilityTraceSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [trace, setTrace] = useState<ObservabilityTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listObservabilityTraces()
      .then(setTraces)
      .catch((e: unknown) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (selected === null) return;
    getObservabilityTrace(selected)
      .then(setTrace)
      .catch((e: unknown) => setError(String(e)));
  }, [selected]);

  const byId = useMemo(() => {
    const map = new Map<string, ObservabilitySpan>();
    for (const s of trace?.spans ?? []) map.set(s.span_id, s);
    return map;
  }, [trace]);

  return (
    <section className="page observability-page">
      <h1>Observabilite -- traces</h1>
      {error && <p className="error">{error}</p>}
      <div className="observability-layout">
        <ul className="trace-list">
          {traces.length === 0 && <li className="empty">Aucune trace (lance un agent).</li>}
          {traces.map((t) => (
            <li key={t.trace_id}>
              <button
                type="button"
                className={t.trace_id === selected ? "trace-row trace-row-active" : "trace-row"}
                onClick={() => setSelected(t.trace_id)}
              >
                <span className="trace-agent">{t.agent_id ?? t.recording_id}</span>
                <span className="trace-meta">
                  {t.target_system ?? ""} -- {t.span_count} span(s)
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="span-tree">
          {trace === null ? (
            <p className="hint">Selectionne une trace pour voir l'arbre de spans.</p>
          ) : (
            <ol>
              {trace.spans.map((s) => (
                <li
                  key={s.span_id}
                  className={`span span-${attr(s, "gen_ai.operation.name") || "node"}`}
                  style={{ paddingLeft: `${spanDepth(s, byId) * 1.5}rem` }}
                >
                  <span className="span-name">{s.name}</span>
                  <span className="span-duration">{Math.round(s.duration_nano / 1000)} us</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </section>
  );
}
