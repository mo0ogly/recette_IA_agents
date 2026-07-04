/**
 * useDeltaFeed -- incremental delta polling for the proxy observability panels.
 *
 * The server exposes delta envelopes ({items, last_seq, reset}): a client
 * polls with its last cursor and receives only the new rows (or a full
 * replacement when the server signals `reset`, e.g. after a clear or a
 * cursor gap). All merge logic lives in the PURE, DOM-free `mergeDelta`;
 * the hook body stays a thin polling shell (interval + busy/alive guards).
 *
 * UI polling only -- this never enters the decision/judge path, so the
 * wall-clock interval does not touch determinism (I4).
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** The server delta envelope. `last_seq` is the server cursor to feed back. */
export interface DeltaEnvelope<T> {
  items: T[];
  last_seq: number;
  reset: boolean;
}

/** Client-side retention cap: the merged list never grows past this many
 *  rows (oldest dropped first). Keeps a long-running panel bounded. */
export const MAX_CLIENT_ITEMS = 2000;

/**
 * Merge a delta envelope into the previous client list.
 *
 * PRECONDITION: both `prev` and `delta.items` are ascending by `seq` (the
 * server emits rows in seq order and this function preserves it), so a
 * concat after filtering collisions keeps ascending order without a sort.
 *
 * - reset: the delta replaces the list entirely.
 * - append: delta items are appended; on a seq collision the delta version
 *   wins (the server may re-emit a row with updated fields).
 * - cap: the merged list is trimmed to `cap` (default MAX_CLIENT_ITEMS),
 *   dropping the OLDEST rows and keeping the newest.
 * - lastSeq is always the server cursor `delta.last_seq`, even when the
 *   delta carries no items (the cursor still advances).
 */
export function mergeDelta<T extends { seq: number }>(
  prev: T[],
  delta: DeltaEnvelope<T>,
  cap?: number,
): { items: T[]; lastSeq: number } {
  const limit = cap ?? MAX_CLIENT_ITEMS;
  if (delta.reset) {
    const items = delta.items.length > limit ? delta.items.slice(-limit) : delta.items;
    return { items, lastSeq: delta.last_seq };
  }
  if (delta.items.length === 0) {
    return { items: prev, lastSeq: delta.last_seq };
  }
  const deltaSeqs = new Set(delta.items.map((item) => item.seq));
  const kept = prev.filter((item) => !deltaSeqs.has(item.seq));
  const merged = kept.concat(delta.items);
  const items = merged.length > limit ? merged.slice(-limit) : merged;
  return { items, lastSeq: delta.last_seq };
}

interface UseDeltaFeedOptions {
  /** Poll cadence in milliseconds. */
  intervalMs: number;
  /** When true, the recurring tick is skipped (the mount fetch still runs). */
  paused: boolean;
  /** Client retention cap; defaults to MAX_CLIENT_ITEMS. */
  cap?: number;
}

interface UseDeltaFeedResult<T> {
  items: T[];
  /** The server cursor, null before the first successful fetch. */
  lastSeq: number | null;
  /** Last fetch error message; cleared on the next successful fetch. */
  error: string | null;
  /** Manual fetch with the current cursor (skipped if one is in flight). */
  refresh: () => Promise<void>;
  /** Clear items/cursor/error and refetch full (server-side filters changed). */
  resetFeed: () => void;
}

/**
 * Poll a delta endpoint and maintain the merged client list.
 *
 * On mount it fetches full (sinceSeq=null), then every `intervalMs` fetches
 * with the current cursor unless paused. An in-flight fetch is never
 * overlapped (busy guard); a failed fetch keeps the old items and surfaces
 * the error, retried on the next tick. `paused` is read through a ref so
 * toggling it does not tear down the interval (the AppTracesPanel pattern).
 */
export function useDeltaFeed<T extends { seq: number }>(
  fetcher: (sinceSeq: number | null) => Promise<DeltaEnvelope<T>>,
  opts: UseDeltaFeedOptions,
): UseDeltaFeedResult<T> {
  const { intervalMs, paused, cap } = opts;
  const [items, setItems] = useState<T[]>([]);
  const [lastSeq, setLastSeq] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Refs so the tick closure always sees current values without re-running
  // the interval effect (pause toggle, cursor advance, fetcher identity).
  const aliveRef = useRef(true);
  const busyRef = useRef(false);
  const lastSeqRef = useRef<number | null>(null);
  const pausedRef = useRef(paused);
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);
  const capRef = useRef(cap);
  useEffect(() => {
    capRef.current = cap;
  }, [cap]);
  // Epoch guard: resetFeed bumps it so a delta that was in flight when the
  // feed was reset is discarded instead of merging stale rows.
  const epochRef = useRef(0);

  const fetchOnce = useCallback(async (sinceSeq: number | null): Promise<void> => {
    if (busyRef.current) {
      return;
    }
    busyRef.current = true;
    const epoch = epochRef.current;
    try {
      const delta = await fetcherRef.current(sinceSeq);
      if (!aliveRef.current || epoch !== epochRef.current) {
        return;
      }
      lastSeqRef.current = delta.last_seq;
      setLastSeq(delta.last_seq);
      setItems((prev) => mergeDelta(prev, delta, capRef.current).items);
      setError(null);
    } catch (err: unknown) {
      if (aliveRef.current && epoch === epochRef.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      busyRef.current = false;
    }
  }, []);

  const refresh = useCallback(
    (): Promise<void> => fetchOnce(lastSeqRef.current),
    [fetchOnce],
  );

  const resetFeed = useCallback((): void => {
    epochRef.current += 1;
    lastSeqRef.current = null;
    setItems([]);
    setLastSeq(null);
    setError(null);
    void fetchOnce(null);
  }, [fetchOnce]);

  useEffect(() => {
    aliveRef.current = true;
    void fetchOnce(null);
    const timer = setInterval(() => {
      if (!pausedRef.current) {
        void fetchOnce(lastSeqRef.current);
      }
    }, intervalMs);
    return () => {
      aliveRef.current = false;
      clearInterval(timer);
    };
  }, [intervalMs, fetchOnce]);

  return { items, lastSeq, error, refresh, resetFeed };
}
