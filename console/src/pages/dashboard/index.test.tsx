/**
 * Dashboard launch KPI test.
 *
 * The api client is mocked so the page renders against known agents/runs and
 * the success/failure KPI cards can be asserted. listRuns drives the tally.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentConfig, Campaign, RunHandle, RunSummary } from "../../types/platform";
import fixture from "./__fixtures__/dashboard.fixture.json";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listAgents: vi.fn(),
    listCampaigns: vi.fn(),
    listRuns: vi.fn(),
    launchLaneB: vi.fn(),
    runCampaign: vi.fn(),
    stopRun: vi.fn(),
    purgeRuns: vi.fn(),
    clearProxyTraces: vi.fn(),
    listAgentActions: vi.fn(),
  };
});

import {
  clearProxyTraces,
  listAgentActions,
  listAgents,
  listCampaigns,
  listRuns,
  purgeRuns,
  runCampaign,
} from "../../api/client";
import DashboardPage from "./index";

const AGENTS = [
  { id: "a1", target_system: "github", runtime: "lab" },
] as unknown as AgentConfig[];

const RUNS = [
  { id: "r1", kind: "lane_b", status: "completed", agent_id: "a1", campaign_id: null, error: null },
  { id: "r2", kind: "lane_b", status: "completed", agent_id: "a1", campaign_id: null, error: null },
  { id: "r3", kind: "lane_b", status: "failed", agent_id: "a1", campaign_id: null, error: "boom" },
  { id: "r4", kind: "lane_b", status: "running", agent_id: "a1", campaign_id: null, error: null },
] as unknown as RunSummary[];

// Real captured campaigns payload (R16 contract gate).
const CAMPAIGNS = fixture.campaigns as unknown as Campaign[];

describe("DashboardPage launch KPI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAgents).mockResolvedValue(AGENTS);
    vi.mocked(listCampaigns).mockResolvedValue([]);
    vi.mocked(listRuns).mockResolvedValue(RUNS);
    vi.mocked(listAgentActions).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the count of successful and failed launches", async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("kpi-succeeded")).toHaveTextContent("2"),
    );
    expect(screen.getByTestId("kpi-failed")).toHaveTextContent("1");
    expect(screen.getByText("launches reussis")).toBeInTheDocument();
    expect(screen.getByText("launches rates")).toBeInTheDocument();
  });

  it("reset tout purges runs and proxy traces after confirm", async () => {
    vi.mocked(purgeRuns).mockResolvedValue({ removed: 3 });
    vi.mocked(clearProxyTraces).mockResolvedValue({ cleared: true });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("kpi-succeeded")).toHaveTextContent("2"));
    fireEvent.click(screen.getByRole("button", { name: "Reset tout" }));
    await waitFor(() => expect(purgeRuns).toHaveBeenCalledTimes(1));
    expect(clearProxyTraces).toHaveBeenCalledTimes(1);
    expect(purgeRuns).toHaveBeenCalledWith();
  });

  it("reset tout does nothing when the confirm is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("kpi-succeeded")).toHaveTextContent("2"));
    fireEvent.click(screen.getByRole("button", { name: "Reset tout" }));
    expect(purgeRuns).not.toHaveBeenCalled();
    expect(clearProxyTraces).not.toHaveBeenCalled();
  });

  it("opens the precise launch modal for an agent row", async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("kpi-succeeded")).toHaveTextContent("2"));
    fireEvent.click(screen.getByRole("button", { name: /lancer precis pour a1/i }));
    // Await the dialog so the modal's async listAgentActions resolves inside act().
    await waitFor(() =>
      expect(
        screen.getByRole("dialog", { name: /lancer une instance precise/i }),
      ).toBeInTheDocument(),
    );
  });
});

describe("DashboardPage campaign launch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAgents).mockResolvedValue(AGENTS);
    vi.mocked(listCampaigns).mockResolvedValue(CAMPAIGNS);
    vi.mocked(listRuns).mockResolvedValue(fixture.runs as unknown as RunSummary[]);
    vi.mocked(listAgentActions).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists campaigns with their step agents from the real payload", async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("camp-pr")).toBeInTheDocument());
    expect(screen.getByText("finance-wire-fraud")).toBeInTheDocument();
    expect(screen.getByText("gh-pr-bot")).toBeInTheDocument();
    expect(screen.getByText("finance-wire-fraud-agent")).toBeInTheDocument();
  });

  it("launches a campaign via runCampaign and disables an active one", async () => {
    vi.mocked(runCampaign).mockResolvedValue({ run_id: "x", status: "running" } as RunHandle);
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("camp-pr")).toBeInTheDocument());
    // camp-pr has a running campaign run in the fixture -> its launch is disabled.
    expect(
      screen.getByRole("button", { name: /lancer la campagne camp-pr/i }),
    ).toBeDisabled();
    // finance-wire-fraud is completed -> launchable.
    fireEvent.click(
      screen.getByRole("button", { name: /lancer la campagne finance-wire-fraud/i }),
    );
    await waitFor(() => expect(runCampaign).toHaveBeenCalledWith("finance-wire-fraud"));
  });

  it("shows an empty state when there is no campaign", async () => {
    vi.mocked(listCampaigns).mockResolvedValue([]);
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText(/aucune campagne/i)).toBeInTheDocument(),
    );
  });

  it("enables the campaign eye when the campaign has a run", async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    // camp-pr has a run in the fixture -> its eye is enabled (run to view).
    const eye = await screen.findByRole("button", { name: "Voir le run de camp-pr" });
    expect(eye).toBeEnabled();
  });

  it("disables the campaign eye until the campaign has a run", async () => {
    vi.mocked(listRuns).mockResolvedValue([]);
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    const eye = await screen.findByRole("button", { name: "Voir le run de camp-pr" });
    expect(eye).toBeDisabled();
  });
});
