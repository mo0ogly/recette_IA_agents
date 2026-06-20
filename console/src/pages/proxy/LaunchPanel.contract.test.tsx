/**
 * R16 contract test for the proxy mini-launcher panel.
 *
 * Fixture in __fixtures__/ was captured from the live backend (/config/agents),
 * not invented. The api client is mocked so the panel renders against the exact
 * shape the backend returns: listAgents resolves the agents array directly.
 *
 * The launcher is AGENT-ONLY: a replayed recording never routes through the
 * tracing proxy (see recette/api/runners.py), so it can never appear in the
 * proxy sessions view. Covers the single launch path (runtime agent ->
 * launchLaneB) and asserts onLaunched receives the resolved run_id. Uses
 * fireEvent (sibling-test convention): @testing-library/user-event is not a
 * dependency of this console.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentConfig, RunHandle } from "../../types/platform";
import agentsFixture from "./__fixtures__/agents.fixture.json";

vi.mock("../../api/client", () => ({
  listAgents: vi.fn(),
  launchLaneB: vi.fn(),
}));

import { launchLaneB, listAgents } from "../../api/client";
import LaunchPanel from "./LaunchPanel";

const agents = agentsFixture as unknown as AgentConfig[];

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
});
