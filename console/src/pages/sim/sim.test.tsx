/**
 * Red-team scenario card + detail tests (R16 contract gate).
 *
 * Fixtures captured from the live API:
 * - scenarios.fixture.json      GET /sim/scenarios     (MAF list, +family)
 * - gitScenarios.fixture.json   GET /sim/git-scenarios (git list, +family)
 * - scenarioDetail.fixture.json GET /sim/scenarios/{id}     (MAF: dims+transcript+action_log)
 * - gitScenarioDetail.fixture.json GET /sim/git-scenarios/{id} (git: dims+goal+action_log)
 * - promote.fixture.json        POST /sim/scenarios/{id}/promote
 *
 * ScenarioList is presentational except for its promote action (it calls
 * promoteSimScenario), so the client is mocked. ScenarioDetail is pure.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { promoteSimScenario } from "../../api/client";
import type { SimPromoteResult, SimScenario, SimScenarioView } from "../../api/client";
import gitScenarioDetailFixture from "./__fixtures__/gitScenarioDetail.fixture.json";
import gitScenariosFixture from "./__fixtures__/gitScenarios.fixture.json";
import mafApprovalDetailFixture from "./__fixtures__/mafApprovalDetail.fixture.json";
import promoteFixture from "./__fixtures__/promote.fixture.json";
import scenarioDetailFixture from "./__fixtures__/scenarioDetail.fixture.json";
import scenariosFixture from "./__fixtures__/scenarios.fixture.json";
import { computeScorecard, Scorecard, ScenarioDetail, ScenarioList } from "./index";

vi.mock("../../api/client", () => ({
  getSimRuns: vi.fn(),
  getSimView: vi.fn(),
  getSimScenarios: vi.fn(),
  getSimGitScenarios: vi.fn(),
  getSimScenario: vi.fn(),
  getSimGitScenario: vi.fn(),
  promoteSimScenario: vi.fn(),
}));

const maf = (scenariosFixture as unknown as { scenarios: SimScenario[] }).scenarios;
const git = (gitScenariosFixture as unknown as { scenarios: SimScenario[] }).scenarios;

beforeEach(() => {
  vi.mocked(promoteSimScenario).mockResolvedValue(promoteFixture as SimPromoteResult);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ScenarioList (cards)", () => {
  it("renders a card per scenario for both families", () => {
    render(<ScenarioList scenarios={[...maf, ...git]} />);
    for (const s of [...maf, ...git]) {
      expect(screen.getByText(s.name)).toBeInTheDocument();
      expect(screen.getByTestId(`sim-scn-card-${s.scenario_id}`)).toBeInTheDocument();
    }
  });

  it("shows a green caught badge (attrapee) for an anomaly-caught scenario", () => {
    render(<ScenarioList scenarios={maf} />);
    const caught = maf.filter((s) => s.anomaly_caught);
    expect(caught.length).toBeGreaterThan(0);
    for (const s of caught) {
      const badge = screen.getByTestId(`sim-scn-caught-${s.scenario_id}`);
      expect(badge).toHaveClass("sim-caught");
      expect(badge).toHaveTextContent("attrapee");
    }
  });

  it("shows a red missed badge (ratee) when anomaly_caught is false", () => {
    const missed: SimScenario = {
      scenario_id: "rt-synthetic-missed",
      name: "Synthetic missed scenario",
      verdict: "correct",
      expected_verdict: "incorrect",
      violation_type: null,
      anomaly_caught: false,
      tags: {},
      family: "maf",
    };
    render(<ScenarioList scenarios={[missed]} />);
    const badge = screen.getByTestId("sim-scn-caught-rt-synthetic-missed");
    expect(badge).toHaveClass("sim-missed");
    expect(badge).toHaveTextContent("ratee");
  });

  it("renders the OWASP ASI standards chip when present", () => {
    render(<ScenarioList scenarios={maf} />);
    expect(screen.getAllByText(/ASI0\d/).length).toBeGreaterThan(0);
  });

  it("covers both verdict variants present in the fixture", () => {
    expect(maf.find((s) => s.verdict === "correct")).toBeDefined();
    expect(maf.find((s) => s.verdict === "incorrect")).toBeDefined();
  });

  it("enables Promote for a caught anomaly (verdict=incorrect)", () => {
    const incorrect = maf.find((s) => s.verdict === "incorrect")!;
    render(<ScenarioList scenarios={maf} />);
    const btn = screen.getByTestId(`sim-scn-promote-${incorrect.scenario_id}`);
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveTextContent("Promouvoir vers le corpus");
  });

  it("disables Promote for a true negative (verdict=correct)", () => {
    const correct = maf.find((s) => s.verdict === "correct")!;
    render(<ScenarioList scenarios={maf} />);
    const btn = screen.getByTestId(`sim-scn-promote-${correct.scenario_id}`);
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "rien a promouvoir");
  });

  it("promotes a caught anomaly and renders the created corpus paths", async () => {
    const incorrect = maf.find((s) => s.verdict === "incorrect")!;
    render(<ScenarioList scenarios={maf} />);
    fireEvent.click(screen.getByTestId(`sim-scn-promote-${incorrect.scenario_id}`));
    // The plain promote passes no overwrite option (back-compat call shape).
    expect(promoteSimScenario).toHaveBeenCalledWith(incorrect.scenario_id, undefined);
    const list = await screen.findByTestId(`sim-scn-promoted-${incorrect.scenario_id}`);
    for (const path of (promoteFixture as SimPromoteResult).created) {
      expect(list).toHaveTextContent(path);
    }
    // Downstream is legible: the promoted subject links to the identification
    // recette (the page that actually scores it), and names the CLI equivalent.
    const next = screen.getByTestId(`sim-scn-promoted-recette-${incorrect.scenario_id}`);
    expect(next).toHaveAttribute("href", "/recette");
    expect(list).toHaveTextContent(`recette redteam-promote ${incorrect.scenario_id}`);
  });

  it("surfaces the API error message when promote fails (non-conflict)", async () => {
    const incorrect = maf.find((s) => s.verdict === "incorrect")!;
    vi.mocked(promoteSimScenario).mockRejectedValueOnce(
      new Error("API request failed (422) on ...: multi-axis"),
    );
    render(<ScenarioList scenarios={maf} />);
    fireEvent.click(screen.getByTestId(`sim-scn-promote-${incorrect.scenario_id}`));
    await waitFor(() =>
      expect(
        screen.getByTestId(`sim-scn-promote-error-${incorrect.scenario_id}`),
      ).toHaveTextContent("multi-axis"),
    );
  });

  it("offers Remplacer on a 409 conflict, then re-promotes with overwrite", async () => {
    const incorrect = maf.find((s) => s.verdict === "incorrect")!;
    // First (plain) promote rejects with the 409 already-exists conflict; the
    // overwrite re-promote (default mock) then succeeds.
    vi.mocked(promoteSimScenario).mockRejectedValueOnce(
      new Error(
        "API request failed (409) on /sim/scenarios/x/promote: subject already exists ... use overwrite to replace",
      ),
    );
    render(<ScenarioList scenarios={maf} />);
    fireEvent.click(screen.getByTestId(`sim-scn-promote-${incorrect.scenario_id}`));

    // The conflict affordance appears (FR line + Remplacer), no raw error dump.
    const overwriteBtn = await screen.findByTestId(
      `sim-scn-overwrite-${incorrect.scenario_id}`,
    );
    expect(
      screen.getByTestId(`sim-scn-conflict-${incorrect.scenario_id}`),
    ).toHaveTextContent("Deja dans le corpus.");
    expect(
      screen.queryByTestId(`sim-scn-promote-error-${incorrect.scenario_id}`),
    ).toBeNull();

    // Click Remplacer -> re-promote with overwrite, created paths render.
    fireEvent.click(overwriteBtn);
    expect(promoteSimScenario).toHaveBeenLastCalledWith(incorrect.scenario_id, {
      overwrite: true,
    });
    const list = await screen.findByTestId(`sim-scn-promoted-${incorrect.scenario_id}`);
    for (const path of (promoteFixture as SimPromoteResult).created) {
      expect(list).toHaveTextContent(path);
    }
  });

  it("calls onSelect with the scenario id when a card is clicked", () => {
    const onSelect = vi.fn();
    render(<ScenarioList scenarios={maf} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId(`sim-scn-card-${maf[0].scenario_id}`));
    expect(onSelect).toHaveBeenCalledWith(maf[0].scenario_id);
  });
});

describe("ScenarioDetail (4-dim matrix + timeline + action log)", () => {
  it("shows the broken axis red and the others green (MAF fixture)", () => {
    const view = scenarioDetailFixture as SimScenarioView;
    render(<ScenarioDetail view={view} />);
    for (const dim of ["identity", "capabilities", "policy", "behavior"] as const) {
      const chip = screen.getByTestId(`sim-scn-dim-${view.scenario_id}-${dim}`);
      expect(chip).toHaveAttribute("data-state", view.dimensions[dim] ? "conform" : "broken");
    }
    // capabilities is the single broken axis in this red-team fixture.
    expect(screen.getByTestId(`sim-scn-dim-${view.scenario_id}-capabilities`)).toHaveAttribute(
      "data-state",
      "broken",
    );
  });

  it("renders the Crescendo escalation transcript turns (MAF fixture)", () => {
    const view = scenarioDetailFixture as SimScenarioView;
    render(<ScenarioDetail view={view} />);
    const timeline = screen.getByTestId(`sim-scn-transcript-${view.scenario_id}`);
    const turns = within(timeline).getAllByRole("listitem");
    expect(turns.length).toBe(view.transcript?.length);
    // The adversary turn carries the data-role marker used to style the escalation.
    expect(timeline.querySelector('[data-role="user"]')).not.toBeNull();
  });

  it("renders the declared capabilities panel with the tool + approval badge (MAF fixture)", () => {
    const view = scenarioDetailFixture as SimScenarioView;
    render(<ScenarioDetail view={view} />);
    const panel = screen.getByTestId(`sim-scn-scope-${view.scenario_id}`);
    // The declared tool (web_search) is shown with its I6 approval badge.
    expect(within(panel).getByText(/web_search\/web_search/)).toBeInTheDocument();
    expect(within(panel).getByText(/approbation : jamais/)).toBeInTheDocument();
  });

  it("marks push hors-perimetre and web_search conforme via the judge, not both flagged (MAF fixture)", () => {
    // The load-bearing fix: the judge's violations drive the marking, NOT a
    // naive approved===false. The declared web_search (approval=never) is
    // legit/conforme; the UNDECLARED push is the real anomaly (hors-perimetre).
    const view = scenarioDetailFixture as SimScenarioView;
    render(<ScenarioDetail view={view} />);
    const log = screen.getByTestId(`sim-scn-actions-${view.scenario_id}`);
    const rows = within(log).getAllByRole("listitem");
    // Match each row by its action-target span (unique per row).
    const byTarget = (target: string): HTMLElement | undefined =>
      rows.find((r) =>
        Array.from(r.querySelectorAll(".sim-action-target")).some(
          (el) => el.textContent === target,
        ),
      );
    const pushRow = byTarget("push");
    const webRow = byTarget("web_search");
    expect(pushRow).toBeDefined();
    expect(webRow).toBeDefined();
    expect(pushRow).toHaveAttribute("data-verdict", "hors-perimetre");
    expect(webRow).toHaveAttribute("data-verdict", "conforme");
    // Exactly one row is flagged -- not both (the bug this fixes).
    expect(rows.filter((r) => r.getAttribute("data-verdict") !== "conforme").length).toBe(1);
  });

  it("marks the I6-gated deploy row 'en attente', web_search conforme (approval-bypass fixture)", () => {
    // I6: the declared approval=always tool (deploy) was invoked unapproved -- it
    // required an approval that was never obtained, so the row reads "en attente",
    // NOT "non approuvee". The declared approval=never web_search stays conforme.
    const view = mafApprovalDetailFixture as SimScenarioView;
    render(<ScenarioDetail view={view} />);
    const log = screen.getByTestId(`sim-scn-actions-${view.scenario_id}`);
    const rows = within(log).getAllByRole("listitem");
    const byTarget = (target: string): HTMLElement | undefined =>
      rows.find((r) =>
        Array.from(r.querySelectorAll(".sim-action-target")).some(
          (el) => el.textContent === target,
        ),
      );
    const deployRow = byTarget("deploy");
    const webRow = byTarget("web_search");
    expect(deployRow).toBeDefined();
    expect(webRow).toBeDefined();
    expect(deployRow).toHaveAttribute("data-verdict", "en-attente");
    expect(webRow).toHaveAttribute("data-verdict", "conforme");
    // The visible FR label conveys pending-approval, not a flat "non approuvee".
    expect(within(deployRow!).getByText(/en attente/)).toBeInTheDocument();
  });

  it("badges the gated deploy turn 'en attente (I6)' on the transcript (approval-bypass fixture)", () => {
    const view = mafApprovalDetailFixture as SimScenarioView;
    render(<ScenarioDetail view={view} />);
    const badge = screen.getByTestId(`sim-scn-turn-pending-${view.scenario_id}`);
    expect(badge).toHaveTextContent("en attente (I6)");
    // The badge sits on the assistant turn that invoked the gated deploy tool.
    const turn = badge.closest('[data-role="assistant"]');
    expect(turn).not.toBeNull();
    expect(within(turn as HTMLElement).getByText("deploy")).toBeInTheDocument();
  });

  it("renders the git goal and action log without a transcript (git fixture)", () => {
    const view = gitScenarioDetailFixture as SimScenarioView;
    render(<ScenarioDetail view={view} />);
    expect(screen.getByText(/Objectif :/)).toBeInTheDocument();
    expect(screen.getByTestId(`sim-scn-actions-${view.scenario_id}`)).toBeInTheDocument();
    expect(screen.queryByTestId(`sim-scn-transcript-${view.scenario_id}`)).toBeNull();
  });

  it("renders the git declared actions and flags the out-of-scope action (git fixture)", () => {
    const view = gitScenarioDetailFixture as SimScenarioView;
    render(<ScenarioDetail view={view} />);
    // Declared scope shows the read-only read_repo capability.
    const panel = screen.getByTestId(`sim-scn-scope-${view.scenario_id}`);
    expect(within(panel).getByText("read_repo")).toBeInTheDocument();
    // The out-of-scope write (open_pr) is flagged hors-perimetre by the judge;
    // the in-scope read_repo stays conforme.
    const log = screen.getByTestId(`sim-scn-actions-${view.scenario_id}`);
    const rows = within(log).getAllByRole("listitem");
    const openPrRow = rows.find((r) => within(r).queryByText("open_pr"));
    const readRow = rows.find((r) => within(r).queryByText("read_repo"));
    expect(openPrRow).toHaveAttribute("data-verdict", "hors-perimetre");
    expect(readRow).toHaveAttribute("data-verdict", "conforme");
  });
});

describe("Scorecard (CLI mirror)", () => {
  it("computes total / caught / missed over both families like recette redteam", () => {
    const all = [...maf, ...git];
    const card = computeScorecard(all);
    // Manual ground truth from the fixtures.
    const caughtAnomalies = all.filter(
      (s) => s.anomaly_caught && s.verdict === "incorrect",
    ).length;
    const conform = all.filter(
      (s) => s.anomaly_caught && s.verdict === "correct",
    ).length;
    const missed = all.filter((s) => !s.anomaly_caught).length;
    expect(card.total).toBe(all.length);
    expect(card.anomaliesCaught).toBe(caughtAnomalies);
    expect(card.conformNoFalseAlarm).toBe(conform);
    expect(card.missed).toBe(missed);
    // caught + missed = total (mirrors the CLI invariant).
    expect(card.anomaliesCaught + card.conformNoFalseAlarm + card.missed).toBe(
      all.length,
    );
  });

  it("groups by OWASP tag, sorted deterministically", () => {
    const card = computeScorecard([...maf, ...git]);
    const tags = card.byOwasp.map(([t]) => t);
    expect(tags).toEqual([...tags].sort());
    const sum = card.byOwasp.reduce((acc, [, n]) => acc + n, 0);
    const tagged = [...maf, ...git].filter((s) => s.tags.owasp_asi).length;
    expect(sum).toBe(tagged);
  });

  it("renders the scorecard chips from the fixtures", () => {
    const all = [...maf, ...git];
    const card = computeScorecard(all);
    render(<Scorecard scenarios={all} />);
    expect(screen.getByTestId("sim-scorecard")).toBeInTheDocument();
    expect(screen.getByTestId("sim-scorecard-total")).toHaveTextContent(String(all.length));
    expect(screen.getByTestId("sim-scorecard-caught")).toHaveTextContent(
      String(card.anomaliesCaught),
    );
    expect(screen.getByTestId("sim-scorecard-missed")).toHaveTextContent(
      String(card.missed),
    );
    for (const [tag, n] of card.byOwasp) {
      expect(screen.getByTestId(`sim-scorecard-owasp-${tag}`)).toHaveTextContent(
        String(n),
      );
    }
  });

  it("shows cross-engine OWASP coverage: ASI04/ASI08 marked covered elsewhere", () => {
    const all = [...maf, ...git];
    render(<Scorecard scenarios={all} />);
    // The cross-engine categories are not /sim scenarios but ARE covered.
    const asi04 = screen.getByTestId("sim-scorecard-cov-ASI04");
    const asi08 = screen.getByTestId("sim-scorecard-cov-ASI08");
    expect(asi04).toHaveAttribute("data-cov", "cross");
    expect(asi04).toHaveTextContent("discovery");
    expect(asi08).toHaveAttribute("data-cov", "cross");
    expect(asi08).toHaveTextContent("orchestration");
    // The coverage count includes the two cross-engine categories (X/10 format).
    expect(screen.getByTestId("sim-scorecard-coverage-count")).toHaveTextContent("/10");
    // A category present in the fixtures is marked "here" (MAF/git).
    const here = new Set(computeScorecard(all).byOwasp.map(([t]) => t));
    for (const tag of here) {
      expect(screen.getByTestId(`sim-scorecard-cov-${tag}`)).toHaveAttribute("data-cov", "here");
    }
  });
});
