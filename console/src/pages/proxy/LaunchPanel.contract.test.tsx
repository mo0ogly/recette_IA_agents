/**
 * R16 contract tests for the proxy mini-launcher panel.
 *
 * Fixtures in __fixtures__/ were captured from the live backend
 * (/config/agents and /recordings), not invented. The api client is mocked so
 * the panel renders against the exact shapes the backend returns:
 *   - listAgents resolves the agents array directly;
 *   - listRecordings resolves the UNWRAPPED recordings array (.recordings).
 * Covers both launch paths (runtime agent -> launchLaneB, recording ->
 * replayRecording) and asserts onLaunched receives the resolved run_id. Uses
 * fireEvent (sibling-test convention): @testing-library/user-event is not a
 * dependency of this console.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentConfig, RecordingMeta, RunHandle } from "../../types/platform";
import agentsFixture from "./__fixtures__/agents.fixture.json";
import recordingsEnvelope from "./__fixtures__/recordings.fixture.json";

vi.mock("../../api/client", () => ({
  listAgents: vi.fn(),
  launchLaneB: vi.fn(),
  listRecordings: vi.fn(),
  replayRecording: vi.fn(),
}));

import { launchLaneB, listAgents, listRecordings, replayRecording } from "../../api/client";
import LaunchPanel from "./LaunchPanel";

const agents = agentsFixture as unknown as AgentConfig[];
const recordings = (recordingsEnvelope as { recordings: RecordingMeta[] }).recordings;

const runHandle = (runId: string): RunHandle => ({
  run_id: runId,
  status: "completed" as RunHandle["status"],
});

afterEach(() => vi.clearAllMocks());

const renderPanel = (onLaunched: (runId: string) => void) =>
  render(
    <MemoryRouter>
      <LaunchPanel onLaunched={onLaunched} />
    </MemoryRouter>,
  );

describe("LaunchPanel (R16 contract)", () => {
  it("launches a runtime agent and reports the run id", async () => {
    vi.mocked(listAgents).mockResolvedValue(agents);
    vi.mocked(launchLaneB).mockResolvedValue(runHandle("R1"));
    const onLaunched = vi.fn();

    renderPanel(onLaunched);

    const entitySelect = await screen.findByLabelText("agent");
    const firstId = agents[0].id;
    await waitFor(() => {
      // +1 for the leading "--" placeholder option.
      expect((entitySelect as HTMLSelectElement).options.length).toBe(agents.length + 1);
    });
    fireEvent.change(entitySelect, { target: { value: firstId } });

    fireEvent.click(screen.getByTestId("proxy-launch-btn"));

    await waitFor(() => {
      expect(launchLaneB).toHaveBeenCalledWith({ agent_id: firstId });
    });
    await waitFor(() => {
      expect(onLaunched).toHaveBeenCalledWith("R1");
    });
  });

  it("replays a recording and reports the run id", async () => {
    vi.mocked(listAgents).mockResolvedValue(agents);
    vi.mocked(listRecordings).mockResolvedValue(recordings);
    vi.mocked(replayRecording).mockResolvedValue(runHandle("R2"));
    const onLaunched = vi.fn();

    renderPanel(onLaunched);

    // Switch the source selector to "recording".
    const modeSelect = await screen.findByLabelText("source");
    fireEvent.change(modeSelect, { target: { value: "recording" } });

    const entitySelect = await screen.findByLabelText("recording");
    const firstRec = recordings[0].recording_id;
    await waitFor(() => {
      // +1 for the leading "--" placeholder option.
      expect((entitySelect as HTMLSelectElement).options.length).toBe(recordings.length + 1);
    });
    fireEvent.change(entitySelect, { target: { value: firstRec } });

    fireEvent.click(screen.getByTestId("proxy-launch-btn"));

    await waitFor(() => {
      expect(replayRecording).toHaveBeenCalledWith(firstRec);
    });
    await waitFor(() => {
      expect(onLaunched).toHaveBeenCalledWith("R2");
    });
  });
});
