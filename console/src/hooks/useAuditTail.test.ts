/**
 * useAuditTail tests (R16 contract gate).
 *
 * The fixture in __fixtures__/auditEvents.fixture.json was captured from the
 * real backend (GET /audit/events) after a real governed flow on a temp event
 * store: deny (action_denied), escalate (action_requested), then a denial
 * resolution (approval_resolved). It carries the { events: [...] } envelope.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listAuditEvents } from "../api/client";
import type { AuditEvent } from "../types/platform";
import auditFixture from "./__fixtures__/auditEvents.fixture.json";
import { STALL_THRESHOLD, useAuditTail } from "./useAuditTail";

vi.mock("../api/client", () => ({
  listAuditEvents: vi.fn(),
}));

const mockListAuditEvents = vi.mocked(listAuditEvents);

// Real backend envelope: { events: [...] }; the client unwraps .events, so the
// mocked client resolves with the bare array (the client contract).
const fixtureEvents = (auditFixture as unknown as { events: AuditEvent[] }).events;
const lastSeq = fixtureEvents[fixtureEvents.length - 1].seq;

/** Synthetic event for buffer-bound tests (shape mirrors the fixture contract). */
function makeEvent(seq: number): AuditEvent {
  return {
    seq,
    event_id: `EVsynth${seq}`,
    schema_version: "2.0",
    kind: "action_executed",
    payload: { agent_id: "synth-bot", target_system: "okta" },
    prev_hash: `hash${seq - 1}`,
    hash: `hash${seq}`,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  mockListAuditEvents.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useAuditTail", () => {
  it("accumulates the first page once and advances the from_seq cursor", async () => {
    mockListAuditEvents.mockResolvedValueOnce(fixtureEvents).mockResolvedValue([]);

    const { result } = renderHook(() => useAuditTail({ intervalMs: 1000 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.events).toHaveLength(fixtureEvents.length);
    expect(result.current.events[0].payload.agent_id).toBe("fixture-bot");
    expect(mockListAuditEvents).toHaveBeenCalledTimes(1);
    expect(mockListAuditEvents.mock.calls[0][0]).toMatchObject({ from_seq: 0 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mockListAuditEvents).toHaveBeenCalledTimes(2);
    // Cursor: last seen seq + 1, so already-stored events are never re-fetched.
    expect(mockListAuditEvents.mock.calls[1][0]).toMatchObject({ from_seq: lastSeq + 1 });
    // Empty page: nothing is appended twice.
    expect(result.current.events).toHaveLength(fixtureEvents.length);
  });

  it("passes agent_id, target_system and kind filters to the client", async () => {
    mockListAuditEvents.mockResolvedValue([]);

    renderHook(() =>
      useAuditTail({
        agentId: "fixture-bot",
        targetSystem: "okta",
        kind: "action_denied",
        intervalMs: 1000,
      }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockListAuditEvents.mock.calls[0][0]).toMatchObject({
      from_seq: 0,
      agent_id: "fixture-bot",
      target_system: "okta",
      kind: "action_denied",
    });
  });

  it("does not poll at all when enabled is false", async () => {
    mockListAuditEvents.mockResolvedValue(fixtureEvents);

    renderHook(() => useAuditTail({ enabled: false, intervalMs: 1000 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(mockListAuditEvents).not.toHaveBeenCalled();
  });

  it("guards against overlapping in-flight polls", async () => {
    let release: (events: AuditEvent[]) => void = () => {};
    mockListAuditEvents.mockImplementationOnce(
      () => new Promise<AuditEvent[]>((resolve) => (release = resolve)),
    );
    mockListAuditEvents.mockResolvedValue([]);

    const { result } = renderHook(() => useAuditTail({ intervalMs: 1000 }));

    await act(async () => {
      // Two intervals elapse while the first request is still in flight.
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(mockListAuditEvents).toHaveBeenCalledTimes(1);

    await act(async () => {
      release(fixtureEvents);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.events).toHaveLength(fixtureEvents.length);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mockListAuditEvents).toHaveBeenCalledTimes(2);
  });

  it("stops polling and ignores in-flight results after unmount", async () => {
    let release: (events: AuditEvent[]) => void = () => {};
    mockListAuditEvents.mockImplementationOnce(
      () => new Promise<AuditEvent[]>((resolve) => (release = resolve)),
    );
    mockListAuditEvents.mockResolvedValue([]);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result, unmount } = renderHook(() => useAuditTail({ intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockListAuditEvents).toHaveBeenCalledTimes(1);

    unmount();
    await act(async () => {
      release(fixtureEvents);
      await vi.advanceTimersByTimeAsync(3000);
    });
    // Interval cleaned up: no further polls after unmount.
    expect(mockListAuditEvents).toHaveBeenCalledTimes(1);
    // In-flight resolution after unmount never lands in state.
    expect(result.current.events).toHaveLength(0);
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it("clear() empties the accumulated tail without resetting the cursor", async () => {
    mockListAuditEvents.mockResolvedValueOnce(fixtureEvents).mockResolvedValue([]);

    const { result } = renderHook(() => useAuditTail({ intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.events).toHaveLength(fixtureEvents.length);

    act(() => {
      result.current.clear();
    });
    expect(result.current.events).toHaveLength(0);

    // A log "clear" must not re-download history: the next poll keeps the
    // advanced cursor instead of falling back to from_seq 0.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mockListAuditEvents.mock.calls[1][0]).toMatchObject({ from_seq: lastSeq + 1 });
    expect(result.current.events).toHaveLength(0);
  });

  it("backfills the first poll with tail=maxEvents, then drops the param", async () => {
    mockListAuditEvents.mockResolvedValueOnce(fixtureEvents).mockResolvedValue([]);

    renderHook(() => useAuditTail({ intervalMs: 1000, maxEvents: 500 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockListAuditEvents.mock.calls[0][0]).toMatchObject({ from_seq: 0, tail: 500 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    // Cursor advanced: the incremental poll must not re-bound the window.
    expect(mockListAuditEvents.mock.calls[1][0]).toMatchObject({
      from_seq: lastSeq + 1,
      tail: undefined,
    });
  });

  it("bounds the buffer to maxEvents and counts evicted events", async () => {
    mockListAuditEvents
      .mockResolvedValueOnce([makeEvent(1), makeEvent(2), makeEvent(3)])
      .mockResolvedValueOnce([makeEvent(4), makeEvent(5)])
      .mockResolvedValue([]);

    const { result } = renderHook(() => useAuditTail({ intervalMs: 1000, maxEvents: 4 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.events).toHaveLength(3);
    expect(result.current.droppedCount).toBe(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    // 5 accumulated, bound 4: the oldest event is evicted and counted.
    expect(result.current.events.map((e) => e.seq)).toEqual([2, 3, 4, 5]);
    expect(result.current.droppedCount).toBe(1);

    // clear() resets the dropped counter with the emptied buffer.
    act(() => {
      result.current.clear();
    });
    expect(result.current.events).toHaveLength(0);
    expect(result.current.droppedCount).toBe(0);
  });

  it("reports stalled after consecutive failures and recovers on success", async () => {
    mockListAuditEvents.mockRejectedValue(new Error("backend down"));

    const { result } = renderHook(() => useAuditTail({ intervalMs: 1000 }));

    // One failure short of the threshold: not stalled yet.
    await act(async () => {
      await vi.advanceTimersByTimeAsync((STALL_THRESHOLD - 2) * 1000);
    });
    expect(result.current.stalled).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.stalled).toBe(true);

    // First success (even an empty page) clears the stall.
    mockListAuditEvents.mockResolvedValue([]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.stalled).toBe(false);
  });

  it("does not warn when unmounted while the backend is failing", async () => {
    mockListAuditEvents.mockRejectedValue(new Error("backend down"));
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { unmount } = renderHook(() => useAuditTail({ intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it("resets cursor, buffer and counters when a filter changes", async () => {
    mockListAuditEvents.mockResolvedValueOnce(fixtureEvents).mockResolvedValue([]);

    const { result, rerender } = renderHook(
      ({ kind }: { kind?: string }) => useAuditTail({ intervalMs: 1000, kind }),
      { initialProps: { kind: undefined as string | undefined } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.events).toHaveLength(fixtureEvents.length);

    mockListAuditEvents.mockClear();
    mockListAuditEvents.mockResolvedValue([]);
    act(() => {
      rerender({ kind: "action_denied" });
    });

    // Events accumulated under the previous filter are gone immediately.
    expect(result.current.events).toHaveLength(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // The new filter restarts from scratch with a bounded backfill.
    expect(mockListAuditEvents.mock.calls[0][0]).toMatchObject({
      from_seq: 0,
      kind: "action_denied",
      tail: 2000,
    });
  });
});
