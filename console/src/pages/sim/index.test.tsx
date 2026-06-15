/**
 * Red-team panel page tests (R16 contract gate).
 *
 * Drives the full SimPage against REAL captured fixtures: the MAF and git
 * scenario lists (cards for both families), and the frozen-recordings stepper.
 * The mock factory lists EVERY sim client function the page imports so no export
 * is silently undefined.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SimPage from "./index";
import {
  getSimGitScenario,
  getSimGitScenarios,
  getSimRuns,
  getSimScenario,
  getSimScenarios,
  getSimView,
} from "../../api/client";
import type { SimScenario, SimScenarioView, SimView } from "../../api/client";
import gitScenarioDetailFixture from "./__fixtures__/gitScenarioDetail.fixture.json";
import gitScenariosFixture from "./__fixtures__/gitScenarios.fixture.json";
import runsFixture from "./__fixtures__/runs.fixture.json";
import scenarioDetailFixture from "./__fixtures__/scenarioDetail.fixture.json";
import scenariosFixture from "./__fixtures__/scenarios.fixture.json";
import viewFixture from "./__fixtures__/view.fixture.json";

vi.mock("../../api/client", () => ({
  getSimRuns: vi.fn(),
  getSimScenarios: vi.fn(),
  getSimGitScenarios: vi.fn(),
  getSimScenario: vi.fn(),
  getSimGitScenario: vi.fn(),
  getSimView: vi.fn(),
  promoteSimScenario: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getSimRuns).mockResolvedValue(runsFixture as { count: number; runs: never[] });
  vi.mocked(getSimView).mockResolvedValue(viewFixture as SimView);
  vi.mocked(getSimScenarios).mockResolvedValue(
    scenariosFixture as { count: number; scenarios: SimScenario[] },
  );
  vi.mocked(getSimGitScenarios).mockResolvedValue(
    gitScenariosFixture as { count: number; scenarios: SimScenario[] },
  );
  vi.mocked(getSimScenario).mockResolvedValue(scenarioDetailFixture as SimScenarioView);
  vi.mocked(getSimGitScenario).mockResolvedValue(gitScenarioDetailFixture as SimScenarioView);
});

afterEach(() => {
  vi.clearAllMocks();
});

const maf = (scenariosFixture as unknown as { scenarios: SimScenario[] }).scenarios;
const git = (gitScenariosFixture as unknown as { scenarios: SimScenario[] }).scenarios;

describe("SimPage", () => {
  it("renders a card for every MAF and git scenario", async () => {
    render(<SimPage />);
    for (const s of maf) {
      expect(await screen.findByTestId(`sim-scn-card-${s.scenario_id}`)).toBeInTheDocument();
    }
    for (const s of git) {
      expect(await screen.findByTestId(`sim-scn-card-${s.scenario_id}`)).toBeInTheDocument();
    }
  });

  it("opens a MAF detail panel with the broken dimension red and the transcript", async () => {
    render(<SimPage />);
    const detail = scenarioDetailFixture as SimScenarioView;
    fireEvent.click(await screen.findByTestId(`sim-scn-card-${detail.scenario_id}`));
    // The four-dimension matrix: the broken axis is red, the others conform.
    for (const dim of ["identity", "capabilities", "policy", "behavior"] as const) {
      const chip = await screen.findByTestId(`sim-scn-dim-${detail.scenario_id}-${dim}`);
      expect(chip).toHaveAttribute("data-state", detail.dimensions[dim] ? "conform" : "broken");
    }
    // The Crescendo escalation transcript renders its turns.
    const timeline = await screen.findByTestId(`sim-scn-transcript-${detail.scenario_id}`);
    expect(within(timeline).getAllByText(/.+/).length).toBeGreaterThan(0);
  });

  it("opens a git detail panel (goal + action log, no transcript)", async () => {
    render(<SimPage />);
    const detail = gitScenarioDetailFixture as SimScenarioView;
    fireEvent.click(await screen.findByTestId(`sim-scn-card-${detail.scenario_id}`));
    expect(
      await screen.findByTestId(`sim-scn-actions-${detail.scenario_id}`),
    ).toBeInTheDocument();
    // The capabilities axis is the broken one in this fixture.
    const cap = await screen.findByTestId(`sim-scn-dim-${detail.scenario_id}-capabilities`);
    expect(cap).toHaveAttribute("data-state", "broken");
  });

  it("renders the frozen-recordings stepper and steps the cursor", async () => {
    render(<SimPage />);
    expect(await screen.findByTestId("sim-run-sim-diagnostic-redteam")).toBeInTheDocument();
    expect(screen.getByTestId("sim-run-sim-diagnostic-clean")).toBeInTheDocument();
    expect(await screen.findByTestId("sim-verdict")).toHaveTextContent("incorrect");
    expect(screen.getByTestId("sim-dim-capabilities")).toHaveAttribute("data-state", "broken");
    expect(screen.getByTestId("sim-stopped")).toHaveTextContent("check_failed");
    expect(screen.getByTestId("sim-checks")).toHaveTextContent("FAIL");

    await screen.findByTestId("sim-cursor");
    expect(screen.getByTestId("sim-cursor")).toHaveTextContent("turn 1/");
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByTestId("sim-cursor")).toHaveTextContent("turn 2/");
  });

  it("shows an inline error when the run list fails", async () => {
    vi.mocked(getSimRuns).mockRejectedValue(new Error("boom"));
    render(<SimPage />);
    await waitFor(() => expect(screen.getByTestId("sim-list-error")).toHaveTextContent("boom"));
  });
});
