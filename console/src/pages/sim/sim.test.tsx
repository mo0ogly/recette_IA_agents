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

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SimScenario } from "../../api/client";
import scenariosFixture from "./__fixtures__/scenarios.fixture.json";
import { ScenarioList } from "./index";

const scenarios = (scenariosFixture as unknown as { scenarios: SimScenario[] }).scenarios;

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
});
