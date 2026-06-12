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
import { useAuditTail } from "./useAuditTail";

vi.mock("../api/client", () => ({
  listAuditEvents: vi.fn(),
}));

const mockListAuditEvents = vi.mocked(listAuditEvents);

// Real backend envelope: { events: [...] }; the client unwraps .events, so the
// mocked client resolves with the bare array (the client contract).
const fixtureEvents = (auditFixture as unknown as { events: AuditEvent[] }).events;
const lastSeq = fixtureEvents[fixtureEvents.length - 1].seq;

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
});
