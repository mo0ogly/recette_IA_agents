/**
 * FluxAnalyzer -- Monaco-based read-only analysis window for the agent flux.
 *
 * Renders the audited event stream for inspection (fold, search, highlight
 * via Monaco built-ins). Strictly read-only: the audit log is immutable (I1),
 * so the editor never accepts input. The Monaco chunk (MonacoJsonViewer) is
 * lazy-loaded and configured for the offline lab (local package + bundled
 * workers, no CDN).
 *
 * Display-layer note: events are rendered verbatim, payload included. This is
 * intentional for the audit audience (RSSI/auditors); access control belongs
 * to the API layer, not to this viewer.
 *
 * Modes:
 * - "event": pretty-printed JSON of the selected event (or a hint when none);
 * - "stream": the whole visible window as JSONL, one event per line, seq
 *   order. Stream refreshes are throttled (STREAM_THROTTLE_MS): the tail can
 *   append every 1.5 s and a full-value swap resets Monaco's scroll/fold
 *   state, so we trade latency for a stable reading surface.
 */

import { Component, Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import type { AuditEvent } from "../types/platform";
import "./FluxAnalyzer.css";

const MonacoJsonViewer = lazy(() => import("./MonacoJsonViewer"));

export type FluxAnalyzerMode = "event" | "stream";

export interface FluxAnalyzerProps {
  events: AuditEvent[];
  /** seq of the event to inspect in "event" mode; null shows a hint. */
  selectedSeq: number | null;
  mode: FluxAnalyzerMode;
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

/**
 * Stable top-level key order so two serializations of one event are diffable.
 * Reorders the top-level keys only; an array replacer cannot be used because it
 * filters keys recursively and would strip nested objects (e.g. `payload`).
 */
function canonicalLine(e: AuditEvent): string {
  const ordered: Record<string, unknown> = {};
  for (const key of Object.keys(e).sort()) {
    ordered[key] = (e as Record<string, unknown>)[key];
  }
  return JSON.stringify(ordered);
}

/** Serialize the analyzer content for the current mode (pure, testable). */
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

export function FluxAnalyzer({ events, selectedSeq, mode }: FluxAnalyzerProps): JSX.Element {
  const value = useMemo(
    () => fluxAnalyzerContent(events, selectedSeq, mode),
    [events, selectedSeq, mode],
  );
  const displayed = useThrottledValue(value, STREAM_THROTTLE_MS, mode !== "stream");

  return (
    <div className="fluxa" data-testid="flux-analyzer">
      <ViewerBoundary>
        <Suspense fallback={<div className="fluxa-loading">loading editor...</div>}>
          <MonacoJsonViewer value={displayed} />
        </Suspense>
      </ViewerBoundary>
    </div>
  );
}
