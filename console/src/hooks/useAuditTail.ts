/**
 * useAuditTail -- incremental polling tail over the append-only audit log (I1).
 *
 * Polls GET /audit/events with a from_seq cursor so each event is fetched and
 * accumulated exactly once. The cursor lives in a ref (last seen seq + 1); a
 * busy ref prevents overlapping in-flight polls when the backend is slower
 * than the interval. Polling stops when `enabled` is false and the interval
 * is cleaned up on unmount (in-flight results are then discarded).
 *
 * v2 hardening:
 * - the FIRST poll backfills with `tail=maxEvents` instead of downloading the
 *   full history (the backend keeps only the last n filtered events);
 * - the buffer is bounded to `maxEvents`: oldest events are evicted and
 *   counted in `droppedCount` (cumulative since mount or last filter change;
 *   `clear()` resets it to 0 without touching the cursor);
 * - `stalled` turns true after 3 consecutive poll failures and false again on
 *   the first success, so a dead backend no longer looks like a quiet log;
 * - changing agentId / targetSystem / kind resets the cursor and the buffer
 *   (events accumulated under the previous filter would otherwise mix in).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { listAuditEvents } from "../api/client";
import type { AuditEvent } from "../types/platform";

export interface UseAuditTailOptions {
  agentId?: string;
  targetSystem?: string;
  kind?: string;
  enabled?: boolean;
  intervalMs?: number;
  /** Buffer bound: oldest events are evicted past this size. */
  maxEvents?: number;
}

export interface AuditTail {
  events: AuditEvent[];
  clear: () => void;
  /** True after STALL_THRESHOLD consecutive poll failures; false on the next success. */
  stalled: boolean;
  /** Events evicted from the bounded buffer since mount or the last filter change. */
  droppedCount: number;
}

const DEFAULT_MAX_EVENTS = 2000;

/** Consecutive poll failures before the tail reports itself as stalled. */
export const STALL_THRESHOLD = 3;

export function useAuditTail(options: UseAuditTailOptions = {}): AuditTail {
  const {
    agentId,
    targetSystem,
    kind,
    enabled = true,
    intervalMs = 1500,
    maxEvents = DEFAULT_MAX_EVENTS,
  } = options;
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [stalled, setStalled] = useState(false);
  const [droppedCount, setDroppedCount] = useState(0);
  const cursorRef = useRef(0);
  const busyRef = useRef(false);
  // True once the first fetch under the current filter succeeded: the
  // bounded backfill (`tail`) is only sent before that, even when the
  // filtered log is still empty (cursor alone cannot tell those apart).
  const backfilledRef = useRef(false);
  // The buffer lives in a ref so eviction accounting stays exact across
  // batches; state copies are published after each mutation.
  const bufferRef = useRef<AuditEvent[]>([]);
  const droppedRef = useRef(0);
  const failuresRef = useRef(0);
  // Read at poll time so a maxEvents change never resets the cursor/buffer.
  const maxRef = useRef(maxEvents);
  maxRef.current = maxEvents;

  const clear = useCallback(() => {
    // Empties the visible tail without resetting the cursor: history is not
    // re-downloaded. The dropped counter restarts with the emptied buffer.
    // `stalled` is deliberately NOT reset: it reports feed health, not
    // buffer content, and clearing the log does not revive the backend.
    bufferRef.current = [];
    droppedRef.current = 0;
    setEvents([]);
    setDroppedCount(0);
  }, []);

  // Filter change: events accumulated under the previous filter no longer
  // belong in the buffer, and the cursor must restart so the new filter's
  // history is backfilled. Declared BEFORE the polling effect so the reset
  // runs first when both fire on the same render.
  useEffect(() => {
    cursorRef.current = 0;
    backfilledRef.current = false;
    bufferRef.current = [];
    droppedRef.current = 0;
    failuresRef.current = 0;
    setEvents([]);
    setDroppedCount(0);
    setStalled(false);
  }, [agentId, targetSystem, kind]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let cancelled = false;

    const poll = async (): Promise<void> => {
      if (busyRef.current) {
        // A previous poll is still in flight: skip this tick (no overlap).
        return;
      }
      busyRef.current = true;
      try {
        const batch = await listAuditEvents({
          from_seq: cursorRef.current,
          // Backfill bound: only the last maxEvents matter to a live tail.
          tail: backfilledRef.current ? undefined : maxRef.current,
          agent_id: agentId,
          target_system: targetSystem,
          kind,
        });
        if (cancelled) {
          return;
        }
        backfilledRef.current = true;
        failuresRef.current = 0;
        setStalled(false);
        if (batch.length === 0) {
          return;
        }
        cursorRef.current = batch[batch.length - 1].seq + 1;
        const next = [...bufferRef.current, ...batch];
        const overflow = next.length - maxRef.current;
        if (overflow > 0) {
          droppedRef.current += overflow;
          bufferRef.current = next.slice(overflow);
        } else {
          bufferRef.current = next;
        }
        setEvents(bufferRef.current);
        setDroppedCount(droppedRef.current);
      } catch {
        // Transient fetch error: keep the cursor, retry on the next tick.
        // Repeated failures surface as `stalled` instead of a silent log.
        if (!cancelled) {
          failuresRef.current += 1;
          if (failuresRef.current >= STALL_THRESHOLD) {
            setStalled(true);
          }
        }
      } finally {
        busyRef.current = false;
      }
    };

    void poll();
    const timer = setInterval(() => {
      void poll();
    }, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [agentId, targetSystem, kind, enabled, intervalMs]);

  return { events, clear, stalled, droppedCount };
}
