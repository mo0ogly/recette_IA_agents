/**
 * useRunStream -- launch a run and stream its frames over the WebSocket.
 *
 * Centralizes the launch -> subscribe -> collect -> stop lifecycle shared by
 * the recette runners (discovery / identification). The caller provides a
 * launch thunk that returns a RunHandle; the hook opens the socket, buffers
 * frames, tracks status, and exposes a cooperative stop.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { openRunSocket, stopRun } from "../api/client";
import type { RunHandle } from "../types/platform";

export interface RunFrame {
  seq: number;
  type: string;
  data: Record<string, unknown>;
}

export interface RunStream {
  runId: string | null;
  status: string;
  frames: RunFrame[];
  error: string | null;
  running: boolean;
  start: (launch: () => Promise<RunHandle>) => Promise<void>;
  stop: () => Promise<void>;
}

export function useRunStream(): RunStream {
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [frames, setFrames] = useState<RunFrame[]>([]);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    return () => socketRef.current?.close();
  }, []);

  const start = useCallback(async (launch: () => Promise<RunHandle>) => {
    setError(null);
    setFrames([]);
    setStatus("pending");
    socketRef.current?.close();
    try {
      const handle = await launch();
      setRunId(handle.run_id);
      setStatus(handle.status);
      const socket = openRunSocket(handle.run_id);
      socketRef.current = socket;
      socket.onopen = () => setStatus("running");
      socket.onmessage = (ev) => {
        const frame = JSON.parse(ev.data as string) as RunFrame;
        setFrames((prev) => [...prev, frame]);
        if (frame.type === "end") {
          setStatus(String(frame.data.status ?? "done"));
          socket.close();
        }
      };
      socket.onerror = () => setError("WebSocket: flux interrompu.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }, []);

  const stop = useCallback(async () => {
    if (runId === null) {
      return;
    }
    try {
      await stopRun(runId);
      setStatus("stopped");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [runId]);

  const running = status === "running" || status === "pending";
  return { runId, status, frames, error, running, start, stop };
}
