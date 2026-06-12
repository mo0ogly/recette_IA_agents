/**
 * FluxAnalyzer -- Monaco-based read-only analysis window for the agent flux.
 *
 * Renders the audited event stream for inspection (fold, search, highlight
 * via Monaco built-ins). Strictly read-only: the audit log is immutable (I1),
 * so the editor never accepts input. The Monaco chunk is lazy-loaded to keep
 * the base bundle small (first runtime dep beyond react/react-router).
 *
 * Modes:
 * - "event": pretty-printed JSON of the selected event (or a hint when none);
 * - "stream": the whole visible window as JSONL, one event per line, seq order.
 */

import { Suspense, lazy, useMemo } from "react";
import type { AuditEvent } from "../types/platform";
import "./FluxAnalyzer.css";

const MonacoEditor = lazy(() => import("@monaco-editor/react"));

export type FluxAnalyzerMode = "event" | "stream";

export interface FluxAnalyzerProps {
  events: AuditEvent[];
  /** seq of the event to inspect in "event" mode; null shows a hint. */
  selectedSeq: number | null;
  mode: FluxAnalyzerMode;
}

/** Hint shown in "event" mode before any line is selected. */
const NO_SELECTION_HINT = JSON.stringify(
  { hint: "select a log line on the left to inspect the event" },
  null,
  2,
);

/** Serialize the analyzer content for the current mode (pure, testable). */
export function fluxAnalyzerContent(
  events: AuditEvent[],
  selectedSeq: number | null,
  mode: FluxAnalyzerMode,
): string {
  if (mode === "stream") {
    return events.map((e) => JSON.stringify(e)).join("\n");
  }
  const selected = events.find((e) => e.seq === selectedSeq);
  return selected === undefined ? NO_SELECTION_HINT : JSON.stringify(selected, null, 2);
}

export function FluxAnalyzer({ events, selectedSeq, mode }: FluxAnalyzerProps): JSX.Element {
  const value = useMemo(
    () => fluxAnalyzerContent(events, selectedSeq, mode),
    [events, selectedSeq, mode],
  );

  return (
    <div className="fluxa" data-testid="flux-analyzer">
      <Suspense fallback={<div className="fluxa-loading">loading editor...</div>}>
        <MonacoEditor
          height="100%"
          language="json"
          theme="vs-dark"
          value={value}
          options={{
            readOnly: true,
            minimap: { enabled: false },
            wordWrap: "on",
            fontSize: 12,
            scrollBeyondLastLine: false,
          }}
        />
      </Suspense>
    </div>
  );
}
