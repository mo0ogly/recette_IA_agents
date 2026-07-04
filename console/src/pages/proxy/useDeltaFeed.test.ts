/**
 * useDeltaFeed tests -- the pure delta merge + the polling hook behind the
 * proxy observability panels.
 *
 * mergeDelta is exercised as a pure function (append+dedupe, reset replace,
 * cap eviction, empty delta cursor advance, order preservation). The hook is
 * driven with fake timers and a mocked fetcher: initial full fetch, cursor
 * tick, pause gating, error retention, resetFeed, and the overlap guard.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MAX_CLIENT_ITEMS, mergeDelta, useDeltaFeed } from "./useDeltaFeed";

interface Row {
  seq: number;
  label: string;
}

function row(seq: number, label = `r${seq}`): Row {
  return { seq, label };
}

describe("mergeDelta", () => {
  it("appends new items and advances the cursor", () => {
    const prev = [row(1), row(2)];
    const out = mergeDelta(prev, { items: [row(3), row(4)], last_seq: 4, reset: false });
    expect(out.items.map((i) => i.seq)).toEqual([1, 2, 3, 4]);
    expect(out.lastSeq).toBe(4);
  });

  it("dedupes by seq with the delta version winning on collision", () => {
    const prev = [row(1), row(2, "old")];
    const out = mergeDelta(prev, { items: [row(2, "new"), row(3)], last_seq: 3, reset: false });
    expect(out.items.map((i) => i.seq)).toEqual([1, 2, 3]);
    expect(out.items[1].label).toBe("new");
  });

  it("replaces everything on reset", () => {
    const prev = [row(1), row(2), row(3)];
    const out = mergeDelta(prev, { items: [row(10), row(11)], last_seq: 11, reset: true });
    expect(out.items.map((i) => i.seq)).toEqual([10, 11]);
    expect(out.lastSeq).toBe(11);
  });

  it("caps the merged list by dropping the OLDEST items", () => {
    const prev = [row(1), row(2), row(3)];
    const out = mergeDelta(prev, { items: [row(4), row(5)], last_seq: 5, reset: false }, 3);
    expect(out.items.map((i) => i.seq)).toEqual([3, 4, 5]);
  });

  it("keeps items and advances lastSeq on an empty delta", () => {
    const prev = [row(1), row(2)];
    const out = mergeDelta(prev, { items: [], last_seq: 9, reset: false });
    expect(out.items).toEqual(prev);
    expect(out.lastSeq).toBe(9);
  });

  it("preserves ascending seq order after a merge with collisions", () => {
    const prev = [row(1), row(3), row(5)];
    const out = mergeDelta(prev, { items: [row(5, "v2"), row(6), row(7)], last_seq: 7, reset: false });
    expect(out.items.map((i) => i.seq)).toEqual([1, 3, 5, 6, 7]);
  });

  it("defaults the cap to MAX_CLIENT_ITEMS", () => {
    const prev = Array.from({ length: MAX_CLIENT_ITEMS }, (_, i) => row(i + 1));
    const out = mergeDelta(prev, {
      items: [row(MAX_CLIENT_ITEMS + 1)],
      last_seq: MAX_CLIENT_ITEMS + 1,
      reset: false,
    });
    expect(out.items).toHaveLength(MAX_CLIENT_ITEMS);
    expect(out.items[0].seq).toBe(2);
    expect(out.items[out.items.length - 1].seq).toBe(MAX_CLIENT_ITEMS + 1);
  });
});

describe("useDeltaFeed", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("runs a full fetch (sinceSeq=null) on mount", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ items: [row(1), row(2)], last_seq: 2, reset: true });
    const { result } = renderHook(() =>
      useDeltaFeed<Row>(fetcher, { intervalMs: 1000, paused: false }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith(null);
    expect(result.current.items.map((i) => i.seq)).toEqual([1, 2]);
    expect(result.current.lastSeq).toBe(2);
    expect(result.current.error).toBeNull();
  });

  it("ticks with the current lastSeq cursor and merges the delta", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ items: [row(1), row(2)], last_seq: 2, reset: true })
      .mockResolvedValueOnce({ items: [row(3)], last_seq: 3, reset: false });
    const { result } = renderHook(() =>
      useDeltaFeed<Row>(fetcher, { intervalMs: 1000, paused: false }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenLastCalledWith(2);
    expect(result.current.items.map((i) => i.seq)).toEqual([1, 2, 3]);
    expect(result.current.lastSeq).toBe(3);
  });

  it("skips ticks while paused and resumes when unpaused", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ items: [], last_seq: 0, reset: true });
    const { rerender } = renderHook(
      ({ paused }: { paused: boolean }) =>
        useDeltaFeed<Row>(fetcher, { intervalMs: 1000, paused }),
      { initialProps: { paused: false } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    rerender({ paused: true });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    rerender({ paused: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("keeps old items and sets error on a failed fetch, then retries", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ items: [row(1)], last_seq: 1, reset: true })
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce({ items: [row(2)], last_seq: 2, reset: false });
    const { result } = renderHook(() =>
      useDeltaFeed<Row>(fetcher, { intervalMs: 1000, paused: false }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.error).toBe("boom");
    expect(result.current.items.map((i) => i.seq)).toEqual([1]);

    // Next tick retries and clears the error.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.error).toBeNull();
    expect(result.current.items.map((i) => i.seq)).toEqual([1, 2]);
  });

  it("resetFeed clears state then refetches full", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ items: [row(1), row(2)], last_seq: 2, reset: true })
      .mockResolvedValueOnce({ items: [row(7)], last_seq: 7, reset: true });
    const { result } = renderHook(() =>
      useDeltaFeed<Row>(fetcher, { intervalMs: 1000, paused: false }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.lastSeq).toBe(2);

    await act(async () => {
      result.current.resetFeed();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenLastCalledWith(null);
    expect(result.current.items.map((i) => i.seq)).toEqual([7]);
    expect(result.current.lastSeq).toBe(7);
  });

  it("re-issues the full fetch when resetFeed lands during an in-flight fetch", async () => {
    let releaseFirst: (v: { items: Row[]; last_seq: number; reset: boolean }) => void = () => {};
    const fetcher = vi
      .fn()
      .mockImplementationOnce(
        () => new Promise((resolve) => (releaseFirst = resolve)),
      )
      .mockResolvedValue({ items: [row(9)], last_seq: 9, reset: true });
    const { result } = renderHook(() =>
      useDeltaFeed<Row>(fetcher, { intervalMs: 1000, paused: false }),
    );
    // The mount fetch is hung in flight.
    expect(fetcher).toHaveBeenCalledTimes(1);

    // resetFeed while busy: its direct fetchOnce(null) is skipped by the
    // busy guard, so only the pending-reset flag can save the refetch.
    act(() => {
      result.current.resetFeed();
    });
    expect(fetcher).toHaveBeenCalledTimes(1); // the direct call was skipped, not issued

    // Resolve the hung (now stale, epoch-discarded) fetch: the pending reset
    // must fire a NEW full fetch immediately -- only microtasks are flushed
    // here, no 1000ms interval tick elapses.
    await act(async () => {
      releaseFirst({ items: [row(1), row(2)], last_seq: 2, reset: true });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenLastCalledWith(null);
    // Final state reflects the fresh fetch; the stale delta was discarded.
    expect(result.current.items.map((i) => i.seq)).toEqual([9]);
    expect(result.current.lastSeq).toBe(9);
    expect(result.current.error).toBeNull();
  });

  it("does not overlap an in-flight fetch (busy guard)", async () => {
    let release: (v: { items: Row[]; last_seq: number; reset: boolean }) => void = () => {};
    const fetcher = vi
      .fn()
      .mockImplementationOnce(
        () => new Promise((resolve) => (release = resolve)),
      )
      .mockResolvedValue({ items: [], last_seq: 1, reset: false });
    renderHook(() => useDeltaFeed<Row>(fetcher, { intervalMs: 1000, paused: false }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    // The mount fetch is still in flight across two intervals -> one call only.
    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      release({ items: [row(1)], last_seq: 1, reset: true });
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("stops polling after unmount", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ items: [], last_seq: 0, reset: true });
    const { unmount } = renderHook(() =>
      useDeltaFeed<Row>(fetcher, { intervalMs: 1000, paused: false }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
