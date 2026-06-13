/**
 * FluxAnalyzer -- Monaco-based read-only analysis window for the agent flux.
 *
 * Renders the audited event stream for inspection (fold, search, highlight
 * via Monaco built-ins). Strictly read-only: the audit log is immutable (I1),
 * so the editor never accepts input. The Monaco chunks (MonacoJsonViewer,
 * MonacoDiffViewer) are lazy-loaded and configured for the offline lab (local
 * package + bundled workers, no CDN).
 *
 * Display-layer note: events are rendered verbatim, payload included. This is
 * intentional for the audit audience (RSSI/auditors); access control belongs
 * to the API layer, not to this viewer.
 *
 * Modes:
 * - "event": pretty-printed JSON of the selected event (or a hint when none);
 * - "stream": the filtered visible window as JSONL, one event per line, seq
 *   order, with governance decorations (verdict colour, approval glyph, risk
 *   heatmap). Stream refreshes are throttled (STREAM_THROTTLE_MS): the tail can
 *   append every 1.5 s and a full-value swap resets Monaco's scroll/fold state,
 *   so we trade latency for a stable reading surface;
 * - "diff": two selected events side by side (DiffEditor), e.g. a request vs
 *   its resolution, or a declared vs effective shape.
 *
 * The semantic helpers (filter, decorations, stream model) live in fluxModel.ts
 * so they are unit-tested against the real audit fixture without Monaco.
 */

import { Component, Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import type { AuditEvent } from "../types/platform";
import {
  buildStreamModel,
  canonicalLine,
  type FluxDecoration,
  type FluxFilter,
  filterEvents,
  streamDecorations,
} from "./fluxModel";
import "./FluxAnalyzer.css";

const MonacoJsonViewer = lazy(() => import("./MonacoJsonViewer"));
const MonacoDiffViewer = lazy(() => import("./MonacoDiffViewer"));

export type FluxAnalyzerMode = "event" | "stream" | "diff";

export interface FluxAnalyzerProps {
  events: AuditEvent[];
  /** seq of the event to inspect in "event" mode; null shows a hint. */
  selectedSeq: number | null;
  mode: FluxAnalyzerMode;
  /** Filter applied to the window in "stream" mode (no-op when empty). */
  filter?: FluxFilter;
  /** [left, right] event seqs compared in "diff" mode. */
  diffSeqs?: [number | null, number | null];
}

/** Minimum interval between stream-mode value refreshes (editor stability). */
export const STREAM_THROTTLE_MS = 2000;

/** Hint shown in "event" mode before any line is selected. */
const NO_SELECTION_HINT = JSON.stringify(
  { hint: "select a log line on the left to inspect the event" },
  null,
  2,
);

/** Hint shown in "stream" mode while the buffer is empty. */
const EMPTY_STREAM_HINT = JSON.stringify({ hint: "no events in the buffer yet" }, null, 2);

/** Hint shown in "diff" mode when a side is not chosen yet. */
const DIFF_HINT = JSON.stringify({ hint: "pick two events (A and B) to compare" }, null, 2);

/** Serialize the analyzer content for event/stream mode (pure, testable). */
export function fluxAnalyzerContent(
  events: AuditEvent[],
  selectedSeq: number | null,
  mode: FluxAnalyzerMode,
): string {
  if (mode === "stream") {
    if (events.length === 0) {
      return EMPTY_STREAM_HINT;
    }
    return events.map(canonicalLine).join("\n");
  }
  const selected = events.find((e) => e.seq === selectedSeq);
  return selected === undefined ? NO_SELECTION_HINT : JSON.stringify(selected, null, 2);
}

/**
 * Throttle a changing value: in bypass mode it passes through synchronously;
 * otherwise updates land at most every `ms` (trailing update guaranteed).
 * UI pacing only -- the decision path is untouched (I4 does not apply here).
 */
function useThrottledValue<T>(value: T, ms: number, bypass: boolean): T {
  const [throttled, setThrottled] = useState(value);
  const lastRef = useRef(0);

  useEffect(() => {
    if (bypass) {
      setThrottled(value);
      return;
    }
    const elapsed = Date.now() - lastRef.current;
    if (elapsed >= ms) {
      lastRef.current = Date.now();
      setThrottled(value);
      return;
    }
    const timer = setTimeout(() => {
      lastRef.current = Date.now();
      setThrottled(value);
    }, ms - elapsed);
    return () => clearTimeout(timer);
  }, [value, ms, bypass]);

  return bypass ? value : throttled;
}

interface BoundaryState {
  error: Error | null;
}

/** Local boundary: a Monaco load failure degrades to a message, not a crash. */
class ViewerBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Render-path failure already captured in state; nothing else to do.
  }

  render(): ReactNode {
    if (this.state.error !== null) {
      return (
        <div className="fluxa-loading" data-testid="flux-analyzer-error">
          editor failed to load: {this.state.error.message}
        </div>
      );
    }
    return this.props.children;
  }
}

/** Pretty JSON of one event by seq, or a hint string when not found. */
function eventJson(events: AuditEvent[], seq: number | null): string {
  const found = events.find((e) => e.seq === seq);
  return found === undefined ? DIFF_HINT : JSON.stringify(found, null, 2);
}

export function FluxAnalyzer({
  events,
  selectedSeq,
  mode,
  filter = {},
  diffSeqs,
}: FluxAnalyzerProps): JSX.Element {
  // Stream mode is the only decorated/filtered surface. Build the model once.
  const stream = useMemo(() => {
    if (mode !== "stream") {
      return null;
    }
    const visible = filterEvents(events, filter);
    if (visible.length === 0) {
      return { text: EMPTY_STREAM_HINT, decorations: [] as FluxDecoration[] };
    }
    const model = buildStreamModel(visible);
    return { text: model.text, decorations: streamDecorations(model.lines) };
  }, [events, mode, filter]);

  const eventValue = useMemo(() => {
    if (mode !== "event") {
      return "";
    }
    return fluxAnalyzerContent(events, selectedSeq, "event");
  }, [events, selectedSeq, mode]);

  // Throttle only the stream text (tail churn); event/diff are user-driven.
  const streamText = useThrottledValue(stream?.text ?? "", STREAM_THROTTLE_MS, mode !== "stream");

  let body: ReactNode;
  if (mode === "diff") {
    const [a, b] = diffSeqs ?? [null, null];
    body = <MonacoDiffViewer original={eventJson(events, a)} modified={eventJson(events, b)} />;
  } else if (mode === "stream") {
    body = <MonacoJsonViewer value={streamText} decorations={stream?.decorations ?? []} />;
  } else {
    body = <MonacoJsonViewer value={eventValue} />;
  }

  return (
    <div className="fluxa" data-testid="flux-analyzer">
      <ViewerBoundary>
        <Suspense fallback={<div className="fluxa-loading">loading editor...</div>}>{body}</Suspense>
      </ViewerBoundary>
    </div>
  );
}
