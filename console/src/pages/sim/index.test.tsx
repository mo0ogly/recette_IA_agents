import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SimPage from "./index";
import { getSimRuns, getSimView } from "../../api/client";
import type { SimView } from "../../api/client";
import runsFixture from "./__fixtures__/runs.fixture.json";
import viewFixture from "./__fixtures__/view.fixture.json";

vi.mock("../../api/client", () => ({
  getSimRuns: vi.fn(),
  getSimView: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getSimRuns).mockResolvedValue(runsFixture as { count: number; runs: never[] });
  vi.mocked(getSimView).mockResolvedValue(viewFixture as SimView);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("SimPage", () => {
  it("lists runs and renders the selected run's verdict, dimensions and turns", async () => {
    render(<SimPage />);
    // both committed runs surface as selectable chips.
    expect(await screen.findByTestId("sim-run-sim-diagnostic-redteam")).toBeInTheDocument();
    expect(screen.getByTestId("sim-run-sim-diagnostic-clean")).toBeInTheDocument();
    // the auto-opened run shows its verdict + the broken dimension + a failing check.
    expect(await screen.findByTestId("sim-verdict")).toHaveTextContent("incorrect");
    expect(screen.getByTestId("sim-dim-capabilities")).toHaveClass("pill-bad");
    expect(screen.getByTestId("sim-stopped")).toHaveTextContent("check_failed");
    expect(screen.getByTestId("sim-checks")).toHaveTextContent("FAIL");
  });

  it("steps the cursor through the transcript", async () => {
    render(<SimPage />);
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
