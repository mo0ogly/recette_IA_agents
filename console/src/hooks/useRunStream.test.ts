/**
 * useRunStream tests -- launch -> subscribe -> collect -> stop lifecycle.
 *
 * The WebSocket is a hand-rolled fake (no network): the test drives onopen /
 * onmessage / onerror directly, mirroring the frame contract of the runs WS
 * ({ seq, type, data }, terminal frame type "end" carrying data.status).
 */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { openRunSocket, stopRun } from "../api/client";
import { useRunStream } from "./useRunStream";

vi.mock("../api/client", () => ({
  openRunSocket: vi.fn(),
  stopRun: vi.fn(),
}));

const mockOpenRunSocket = vi.mocked(openRunSocket);
const mockStopRun = vi.mocked(stopRun);

class FakeSocket {
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  close(): void {
    this.closed = true;
  }
}

function frame(seq: number, type: string, data: Record<string, unknown> = {}): string {
  return JSON.stringify({ seq, type, data });
}

beforeEach(() => {
  mockOpenRunSocket.mockReset();
  mockStopRun.mockReset();
});

describe("useRunStream", () => {
  it("starts a run, streams frames, and ends with the terminal status", async () => {
    const socket = new FakeSocket();
    mockOpenRunSocket.mockReturnValue(socket as unknown as WebSocket);
    const { result } = renderHook(() => useRunStream());

    await act(async () => {
      await result.current.start(async () => ({ run_id: "r1", status: "pending" }));
    });
    expect(result.current.runId).toBe("r1");
    expect(result.current.status).toBe("pending");
    expect(result.current.running).toBe(true);

    act(() => socket.onopen?.());
    expect(result.current.status).toBe("running");

    act(() => {
      socket.onmessage?.({ data: frame(0, "step", { index: 0 }) });
      socket.onmessage?.({ data: frame(1, "end", { status: "completed" }) });
    });
    expect(result.current.frames.map((f) => f.type)).toEqual(["step", "end"]);
    expect(result.current.status).toBe("completed");
    expect(result.current.running).toBe(false);
    expect(socket.closed).toBe(true);
  });

  it("maps a launch failure to status error with the message", async () => {
    const { result } = renderHook(() => useRunStream());
    await act(async () => {
      await result.current.start(async () => {
        throw new Error("HTTP 404");
      });
    });
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("HTTP 404");
    expect(result.current.running).toBe(false);
    expect(mockOpenRunSocket).not.toHaveBeenCalled();
  });

  it("reports a socket error without losing collected frames", async () => {
    const socket = new FakeSocket();
    mockOpenRunSocket.mockReturnValue(socket as unknown as WebSocket);
    const { result } = renderHook(() => useRunStream());
    await act(async () => {
      await result.current.start(async () => ({ run_id: "r1", status: "pending" }));
    });
    act(() => {
      socket.onmessage?.({ data: frame(0, "step", {}) });
      socket.onerror?.();
    });
    expect(result.current.error).toBe("WebSocket: flux interrompu.");
    expect(result.current.frames).toHaveLength(1);
  });

  it("stop calls the API and flips the status to stopped", async () => {
    const socket = new FakeSocket();
    mockOpenRunSocket.mockReturnValue(socket as unknown as WebSocket);
    mockStopRun.mockResolvedValue(undefined as never);
    const { result } = renderHook(() => useRunStream());
    await act(async () => {
      await result.current.start(async () => ({ run_id: "r1", status: "pending" }));
    });
    await act(async () => {
      await result.current.stop();
    });
    expect(mockStopRun).toHaveBeenCalledWith("r1");
    expect(result.current.status).toBe("stopped");
  });

  it("stop is a no-op before any run started", async () => {
    const { result } = renderHook(() => useRunStream());
    await act(async () => {
      await result.current.stop();
    });
    expect(mockStopRun).not.toHaveBeenCalled();
  });

  it("a new start clears previous frames and closes the previous socket", async () => {
    const first = new FakeSocket();
    const second = new FakeSocket();
    mockOpenRunSocket.mockReturnValueOnce(first as unknown as WebSocket);
    mockOpenRunSocket.mockReturnValueOnce(second as unknown as WebSocket);
    const { result } = renderHook(() => useRunStream());
    await act(async () => {
      await result.current.start(async () => ({ run_id: "r1", status: "pending" }));
    });
    act(() => first.onmessage?.({ data: frame(0, "step", {}) }));
    await act(async () => {
      await result.current.start(async () => ({ run_id: "r2", status: "pending" }));
    });
    expect(first.closed).toBe(true);
    expect(result.current.frames).toHaveLength(0);
    expect(result.current.runId).toBe("r2");
  });
});
