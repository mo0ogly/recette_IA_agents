/**
 * useAuditTail -- incremental polling tail over the append-only audit log (I1).
 *
 * Polls GET /audit/events with a from_seq cursor so each event is fetched and
 * accumulated exactly once. The cursor lives in a ref (last seen seq + 1); a
 * busy ref prevents overlapping in-flight polls when the backend is slower
 * than the interval. Polling stops when `enabled` is false and the interval
 * is cleaned up on unmount (in-flight results are then discarded).
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
}

export interface AuditTail {
  events: AuditEvent[];
  clear: () => void;
}

export function useAuditTail(options: UseAuditTailOptions = {}): AuditTail {
  const { agentId, targetSystem, kind, enabled = true, intervalMs = 1500 } = options;
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const cursorRef = useRef(0);
  const busyRef = useRef(false);

  const clear = useCallback(() => {
    setEvents([]);
  }, []);

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
          agent_id: agentId,
          target_system: targetSystem,
          kind,
        });
        if (cancelled || batch.length === 0) {
          return;
        }
        cursorRef.current = batch[batch.length - 1].seq + 1;
        setEvents((prev) => [...prev, ...batch]);
      } catch {
        // Transient fetch error: keep the cursor, retry on the next tick.
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

  return { events, clear };
}
