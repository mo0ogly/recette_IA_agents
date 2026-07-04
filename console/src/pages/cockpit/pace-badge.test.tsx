/**
 * Tests for the Cockpit active-pace badge (legibility-first).
 *
 * When the selected/running agent has an effective pacing delay (pace_ms > 0)
 * the cockpit shows a small "pace {n}ms" badge next to the live-flow header, so
 * an operator immediately sees the agent is deliberately slowed. Presentation
 * only -- no run/streaming logic is involved.
 *
 * The servers list is not in scope in the cockpit, so the effective pace is the
 * agent's own pace_ms (fallback documented in the component). The fixture's
 * first agent carries pace_ms: 800; the others carry none (effective pace 0).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import pacedAgentsFixture from "../agents/__fixtures__/agents-with-pace.fixture.json";
import backendsFixture from "../agents/__fixtures__/ai-backends.fixture.json";
import type { AgentConfig, AiBackend } from "../../types/platform";

vi.mock("../../components/MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => (
    <textarea readOnly data-testid="monaco-stub" value={value} />
  ),
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listAgents: vi.fn(),
    listAiBackends: vi.fn(),
    launchLaneB: vi.fn(),
    openRunSocket: vi.fn(),
    stopRun: vi.fn(),
    getProxyTraces: vi.fn(),
  };
});

import {
  getProxyTraces,
  listAgents,
  listAiBackends,
} from "../../api/client";
import CockpitPage from "./index";

describe("CockpitPage pace badge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAiBackends).mockResolvedValue(backendsFixture as AiBackend[]);
    vi.mocked(getProxyTraces).mockResolvedValue({ debug_enabled: true, traces: [], last_seq: 0, total: 0, reset: false });
  });

  it("shows a pace badge for the selected agent whose pace_ms > 0", async () => {
    vi.mocked(listAgents).mockResolvedValue(pacedAgentsFixture as AgentConfig[]);

    render(<CockpitPage />);

    // The first fixture agent (camp-rogue-bot) carries pace_ms: 800 and is
    // auto-selected, so the badge is visible without any interaction.
    expect(await screen.findByText(/pace 800ms/)).toBeInTheDocument();
  });

  it("shows no pace badge for a selected agent with effective pace 0", async () => {
    vi.mocked(listAgents).mockResolvedValue(pacedAgentsFixture as AgentConfig[]);

    render(<CockpitPage />);

    // Wait for the picker to populate, then select an agent that carries no
    // pace_ms (camp-identity-admin, effective pace 0).
    await screen.findByText(/pace 800ms/);
    // The launch "Agent" picker is the combobox whose options are the agent ids
    // (a second "Agent" combobox is the network-log filter). Pick it by option.
    const launchPicker = screen
      .getAllByRole("combobox", { name: "Agent" })
      .find((el) =>
        Array.from((el as HTMLSelectElement).options).some(
          (o) => o.value === "camp-identity-admin",
        ),
      );
    if (launchPicker === undefined) {
      throw new Error("launch Agent picker not found");
    }
    fireEvent.change(launchPicker, { target: { value: "camp-identity-admin" } });

    await waitFor(() => {
      expect(screen.queryByText(/pace \d+ms/)).not.toBeInTheDocument();
    });
  });
});
