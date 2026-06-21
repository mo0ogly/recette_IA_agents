/**
 * R16 contract test for ReplayDiffPanel (the "replay-diff" proxy source).
 *
 * The api client is mocked: one recording, a replay that returns a run handle,
 * and run events shaped exactly like the backend's `/runs/:id/events` (ordered
 * frames, a terminal `result` frame so no real polling delay). Two replays of the
 * same recording return the same mocked events -> the line-aligned diff is all
 * `same` -> the panel must surface the "identique (I4)" determinism marker.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RecordingMeta, RunEvent } from "../../types/platform";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listRecordings: vi.fn(),
    replayRecording: vi.fn(),
    getRunEvents: vi.fn(),
  };
});

import { getRunEvents, listRecordings, replayRecording } from "../../api/client";
import ReplayDiffPanel from "./ReplayDiffPanel";

const RECORDING: RecordingMeta = {
  recording_id: "rec-001",
  agent_id: "agent-a",
  target_system: "github",
  goal: "open a PR",
  provider: "stub",
  steps: 2,
};

// Terminal frame present (`result`) so the panel's poll stops on the first read.
const EVENTS: RunEvent[] = [
  { type: "agent_start" },
  { type: "tool_call", data: { name: "read_repo", args: { resource: "acme/x" } } },
  { type: "tool_call", data: { name: "open_pr", args: { resource: "acme/x" } } },
  { type: "result", data: { actions: [] } },
];

describe("ReplayDiffPanel (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listRecordings).mockResolvedValue([RECORDING]);
    vi.mocked(replayRecording).mockResolvedValue({ run_id: "run-xyz", status: "completed" });
    vi.mocked(getRunEvents).mockResolvedValue(EVENTS);
  });

  it("lists recordings and replays-then-diffs twice, showing the I4 identique marker", async () => {
    render(<ReplayDiffPanel />);

    // The recording is selectable.
    const select = (await screen.findByTestId("replay-diff-select")) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("rec-001"));

    // Click "Rejouer + diff": two replays of the same recording.
    fireEvent.click(screen.getByTestId("replay-diff-run"));

    // The diff region appears and the two identical replays prove determinism.
    expect(await screen.findByTestId("replay-diff")).toBeInTheDocument();
    expect(await screen.findByTestId("replay-diff-identical")).toHaveTextContent(
      "identique (I4)",
    );
    // Determinism is proven by replaying twice.
    await waitFor(() => expect(replayRecording).toHaveBeenCalledTimes(2));
  });

  it("surfaces a load error instead of crashing", async () => {
    vi.mocked(listRecordings).mockRejectedValue(new Error("recordings down"));
    render(<ReplayDiffPanel />);
    expect(await screen.findByText(/recordings down/)).toBeInTheDocument();
  });

  it("surfaces a replay error inline, no crash", async () => {
    vi.mocked(replayRecording).mockRejectedValue(new Error("replay failed"));
    render(<ReplayDiffPanel />);
    await screen.findByTestId("replay-diff-select");
    fireEvent.click(screen.getByTestId("replay-diff-run"));
    expect(await screen.findByText(/replay failed/)).toBeInTheDocument();
  });
});
