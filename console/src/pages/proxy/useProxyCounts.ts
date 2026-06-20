/**
 * useProxyCounts -- background poll feeding the Proxy source-menu badges.
 *
 * Polls the three LIGHTWEIGHT status endpoints (debug trace count, wire flow
 * count, reconcile verdict+bypass count) so every source carries a live badge
 * in the menu even when its panel is closed -- without mounting the panel and
 * without the heavy full-payload reads. The reconcile status is the new
 * count-only endpoint (GET /proxy/reconcile/status): it runs the same join but
 * returns just {ok, bypass_count}, so the menu never re-renders the bypass list
 * just to show a number.
 *
 * UI polling only -- it never enters the decision/judge path, so a wall-clock
 * interval here does not touch determinism (I4). An in-flight poll is not
 * overlapped, a failed endpoint keeps the previous value (Promise.allSettled),
 * and an in-flight result that resolves after unmount is dropped (alive guard).
 */

import { useEffect, useState } from "react";

import { getProxyDebugStatus, getReconcileStatus, getWireStatus } from "../../api/client";
import type { SourceId, SourceStatus } from "./proxyMenu";

const POLL_INTERVAL_MS = 5000;

interface UseProxyCountsOptions {
  /** Poll cadence; defaults to 5s (badges are at-a-glance, not real-time). */
  intervalMs?: number;
}

/** A per-source status map for the menu badges. Sources whose endpoint has not
 *  answered yet are simply absent (the menu shows no badge for them). */
export default function useProxyCounts(
  options: UseProxyCountsOptions = {},
): Partial<Record<SourceId, SourceStatus>> {
  const intervalMs = options.intervalMs ?? POLL_INTERVAL_MS;
  const [counts, setCounts] = useState<Partial<Record<SourceId, SourceStatus>>>({});

  useEffect(() => {
    let alive = true;
    let busy = false;

    const tick = async (): Promise<void> => {
      if (busy) {
        return;
      }
      busy = true;
      try {
        const [app, wire, reconcile] = await Promise.allSettled([
          getProxyDebugStatus(),
          getWireStatus(),
          getReconcileStatus(),
        ]);
        if (!alive) {
          return;
        }
        setCounts((prev) => {
          const next: Partial<Record<SourceId, SourceStatus>> = { ...prev };
          if (app.status === "fulfilled") {
            next.app = { count: app.value.trace_count, disabled: !app.value.debug_enabled };
          }
          if (wire.status === "fulfilled") {
            next.wire = { count: wire.value.flow_count, disabled: !wire.value.enabled };
          }
          if (reconcile.status === "fulfilled") {
            next.reconcile = {
              count: reconcile.value.bypass_count,
              failed: reconcile.value.bypass_count,
            };
          }
          return next;
        });
      } finally {
        busy = false;
      }
    };

    void tick();
    const timer = setInterval(() => void tick(), intervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return counts;
}
