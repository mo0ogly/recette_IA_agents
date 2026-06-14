/**
 * Red-team scenario list tests (R16 contract gate).
 *
 * The fixture in __fixtures__/scenarios.fixture.json was captured from the live
 * API (GET /sim/scenarios) after the two committed scenarios were replayed -- it
 * carries the { count, scenarios: [...] } envelope with one "incorrect" and one
 * "correct" verdict, both anomaly_caught, each with an owasp_asi tag. ScenarioList
 * is a pure presentational component, so it is rendered directly against the real
 * payload (no client mocking needed).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { promoteSimScenario } from "../../api/client";
import type { SimPromoteResult, SimScenario } from "../../api/client";
import promoteFixture from "./__fixtures__/promote.fixture.json";
import scenariosFixture from "./__fixtures__/scenarios.fixture.json";
import { ScenarioList } from "./index";

// ScenarioList is presentational EXCEPT for the promote action, which calls the
// API. The unit test mocks that single call (no live API); the resolved value is
// the REAL captured promote payload (__fixtures__/promote.fixture.json).
vi.mock("../../api/client", () => ({
  promoteSimScenario: vi.fn(),
}));

const scenarios = (scenariosFixture as unknown as { scenarios: SimScenario[] }).scenarios;

beforeEach(() => {
  vi.mocked(promoteSimScenario).mockResolvedValue(promoteFixture as SimPromoteResult);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ScenarioList", () => {
  it("renders without crashing and shows a row per scenario", () => {
    render(<ScenarioList scenarios={scenarios} />);
    for (const s of scenarios) {
      expect(screen.getByText(s.name)).toBeInTheDocument();
    }
  });

  it("shows a caught badge (pill-ok) for each anomaly-caught scenario", () => {
    render(<ScenarioList scenarios={scenarios} />);
    const caught = scenarios.filter((s) => s.anomaly_caught);
    expect(caught.length).toBeGreaterThan(0);
    for (const s of caught) {
      const badge = screen.getByTestId(`sim-scn-caught-${s.scenario_id}`);
      expect(badge).toHaveClass("pill", "pill-ok");
      expect(badge).toHaveTextContent("caught");
    }
  });

  it("reflects anomaly_caught=false with pill-bad and a 'missed' label", () => {
    const missed: SimScenario = {
      scenario_id: "rt-synthetic-missed",
      name: "Synthetic missed scenario",
      verdict: "correct",
      expected_verdict: "incorrect",
      violation_type: null,
      anomaly_caught: false,
      tags: {},
    };
    render(<ScenarioList scenarios={[missed]} />);
    const badge = screen.getByTestId("sim-scn-caught-rt-synthetic-missed");
    expect(badge).toHaveClass("pill", "pill-bad");
    expect(badge).toHaveTextContent("missed");
  });

  it("renders the OWASP ASI tag when present", () => {
    render(<ScenarioList scenarios={scenarios} />);
    const tagged = scenarios.filter((s) => s.tags.owasp_asi);
    expect(tagged.length).toBeGreaterThan(0);
    // At least one ASI0x tag is surfaced in the DOM.
    expect(screen.getAllByText(/ASI0\d/).length).toBeGreaterThan(0);
  });

  it("covers both verdict variants present in the fixture (correct + incorrect)", () => {
    const correct = scenarios.find((s) => s.verdict === "correct");
    const incorrect = scenarios.find((s) => s.verdict === "incorrect");
    expect(correct).toBeDefined();
    expect(incorrect).toBeDefined();
    render(<ScenarioList scenarios={scenarios} />);
    // Both rows expose their predicted-vs-expected verdict.
    if (correct) {
      const okBadge = screen.getByTestId(`sim-scn-caught-${correct.scenario_id}`);
      expect(okBadge).toHaveClass(correct.anomaly_caught ? "pill-ok" : "pill-bad");
    }
    if (incorrect) {
      const koBadge = screen.getByTestId(`sim-scn-caught-${incorrect.scenario_id}`);
      expect(koBadge).toHaveClass(incorrect.anomaly_caught ? "pill-ok" : "pill-bad");
    }
  });

  it("offers an enabled Promote button for a caught anomaly (verdict=incorrect)", () => {
    const incorrect = scenarios.find((s) => s.verdict === "incorrect");
    expect(incorrect).toBeDefined();
    render(<ScenarioList scenarios={scenarios} />);
    const btn = screen.getByTestId(`sim-scn-promote-${incorrect!.scenario_id}`);
    expect(btn).toBeInTheDocument();
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveTextContent("Promote to corpus");
  });

  it("disables Promote for a true negative (verdict=correct: nothing to promote)", () => {
    const correct = scenarios.find((s) => s.verdict === "correct");
    expect(correct).toBeDefined();
    render(<ScenarioList scenarios={scenarios} />);
    const btn = screen.getByTestId(`sim-scn-promote-${correct!.scenario_id}`);
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "nothing to promote");
  });

  it("promotes a caught anomaly and renders the created corpus paths", async () => {
    const incorrect = scenarios.find((s) => s.verdict === "incorrect");
    expect(incorrect).toBeDefined();
    render(<ScenarioList scenarios={scenarios} />);
    fireEvent.click(screen.getByTestId(`sim-scn-promote-${incorrect!.scenario_id}`));
    expect(promoteSimScenario).toHaveBeenCalledWith(incorrect!.scenario_id);
    const list = await screen.findByTestId(`sim-scn-promoted-${incorrect!.scenario_id}`);
    for (const path of (promoteFixture as SimPromoteResult).created) {
      expect(list).toHaveTextContent(path);
    }
  });

  it("surfaces the API error message when promote fails", async () => {
    const incorrect = scenarios.find((s) => s.verdict === "incorrect");
    expect(incorrect).toBeDefined();
    vi.mocked(promoteSimScenario).mockRejectedValueOnce(new Error("already promoted"));
    render(<ScenarioList scenarios={scenarios} />);
    fireEvent.click(screen.getByTestId(`sim-scn-promote-${incorrect!.scenario_id}`));
    await waitFor(() =>
      expect(
        screen.getByTestId(`sim-scn-promote-error-${incorrect!.scenario_id}`),
      ).toHaveTextContent("already promoted"),
    );
  });
});
