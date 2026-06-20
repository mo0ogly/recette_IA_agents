/**
 * useProxyCounts tests -- the background poll that feeds the source-menu badges.
 *
 * The three status endpoints are mocked; the hook is driven through fake timers.
 * Covers: the three badges populate from the status payloads, a failed endpoint
 * keeps the previous value, the in-flight poll is not overlapped, and the
 * interval is cleaned up on unmount.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getProxyDebugStatus,
  getReconcileStatus,
  getWireStatus,
} from "../../api/client";
import useProxyCounts from "./useProxyCounts";

vi.mock("../../api/client", () => ({
  getProxyDebugStatus: vi.fn(),
  getWireStatus: vi.fn(),
  getReconcileStatus: vi.fn(),
}));

const mockDebug = vi.mocked(getProxyDebugStatus);
const mockWire = vi.mocked(getWireStatus);
const mockReconcile = vi.mocked(getReconcileStatus);

beforeEach(() => {
  vi.useFakeTimers();
  mockDebug.mockReset();
  mockWire.mockReset();
  mockReconcile.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useProxyCounts", () => {
  it("populates a badge for every source from the status payloads", async () => {
    mockDebug.mockResolvedValue({ debug_enabled: true, trace_count: 4 });
    mockWire.mockResolvedValue({ enabled: false, proxy_url: null, flow_count: 0 });
    mockReconcile.mockResolvedValue({ ok: false, bypass_count: 2 });

    const { result } = renderHook(() => useProxyCounts({ intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.app).toEqual({ count: 4, disabled: false });
    expect(result.current.wire).toEqual({ count: 0, disabled: true });
    expect(result.current.reconcile).toEqual({ count: 2, failed: 2 });
  });

  it("keeps the previous value for an endpoint that fails", async () => {
    mockDebug.mockResolvedValue({ debug_enabled: true, trace_count: 1 });
    mockWire.mockResolvedValue({ enabled: true, proxy_url: "http://x", flow_count: 3 });
    mockReconcile.mockResolvedValueOnce({ ok: true, bypass_count: 0 });

    const { result } = renderHook(() => useProxyCounts({ intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.reconcile).toEqual({ count: 0, failed: 0 });

    // Next poll: reconcile rejects -> its badge stays at the last good value,
    // while app/wire keep refreshing.
    mockReconcile.mockRejectedValue(new Error("reconcile down"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.reconcile).toEqual({ count: 0, failed: 0 });
    expect(result.current.wire).toEqual({ count: 3, disabled: false });
  });

  it("does not overlap an in-flight poll", async () => {
    let release: (v: { ok: boolean; bypass_count: number }) => void = () => {};
    mockDebug.mockResolvedValue({ debug_enabled: true, trace_count: 0 });
    mockWire.mockResolvedValue({ enabled: false, proxy_url: null, flow_count: 0 });
    mockReconcile.mockImplementationOnce(
      () => new Promise((resolve) => (release = resolve)),
    );
    mockReconcile.mockResolvedValue({ ok: true, bypass_count: 0 });

    renderHook(() => useProxyCounts({ intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    // First poll still in flight across two intervals -> reconcile called once.
    expect(mockReconcile).toHaveBeenCalledTimes(1);

    await act(async () => {
      release({ ok: true, bypass_count: 0 });
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mockReconcile).toHaveBeenCalledTimes(2);
  });

  it("stops polling after unmount", async () => {
    mockDebug.mockResolvedValue({ debug_enabled: true, trace_count: 0 });
    mockWire.mockResolvedValue({ enabled: false, proxy_url: null, flow_count: 0 });
    mockReconcile.mockResolvedValue({ ok: true, bypass_count: 0 });

    const { unmount } = renderHook(() => useProxyCounts({ intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockDebug).toHaveBeenCalledTimes(1);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(mockDebug).toHaveBeenCalledTimes(1);
  });
});
