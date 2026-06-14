/**
 * R16 contract tests for the Verdicts page.
 *
 * Fixtures in __fixtures__/ were captured from the real backend
 * (recette.api running locally against temp config/event-store/verdicts
 * paths), not invented. The api client module is mocked so the page renders
 * against the exact payload shapes the backend returns.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { VerdictScorecard, VerdictSubmission } from "../../types/platform";
import verdictsFixture from "./__fixtures__/verdicts.fixture.json";
import scorecardFixture from "./__fixtures__/scorecard.fixture.json";
import scorecardNaFixture from "./__fixtures__/scorecard-na.fixture.json";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    getVerdicts: vi.fn(),
    getVerdictScorecard: vi.fn(),
    getVerdictHistory: vi.fn(),
    postVerdicts: vi.fn(),
    listAuditEvents: vi.fn(),
  };
});

import {
  getVerdictHistory,
  getVerdictScorecard,
  getVerdicts,
  listAuditEvents,
  postVerdicts,
} from "../../api/client";
import VerdictsPage from "./index";

const verdicts = verdictsFixture as VerdictSubmission;
const scorecard = scorecardFixture as VerdictScorecard;
const scorecardNa = scorecardNaFixture as VerdictScorecard;

function renderPage(): void {
  render(
    <MemoryRouter>
      <VerdictsPage />
    </MemoryRouter>,
  );
}

function mockLoaded(card: VerdictScorecard = scorecard): void {
  vi.mocked(getVerdicts).mockResolvedValue(verdicts);
  vi.mocked(getVerdictScorecard).mockResolvedValue(card);
  vi.mocked(getVerdictHistory).mockResolvedValue([verdicts]);
}

/** The table row of one judged agent, located by its agent_id cell. */
async function rowOf(agentId: string): Promise<HTMLElement> {
  const cell = await screen.findByText(agentId);
  const row = cell.closest("tr");
  if (row === null) {
    throw new Error(`no table row for agent ${agentId}`);
  }
  return row;
}

describe("VerdictsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The bottom LogConsole tails the audit log; keep it empty here.
    vi.mocked(listAuditEvents).mockResolvedValue([]);
    // History panel: default to empty unless a test opts in via mockLoaded.
    vi.mocked(getVerdictHistory).mockResolvedValue([]);
  });

  it("renders the scorecard banner with all captured numbers", async () => {
    mockLoaded();

    renderPage();

    const banner = await screen.findByTestId("verdict-scorecard");
    expect(within(banner).getByTestId("scorecard-total")).toHaveTextContent("4");
    expect(within(banner).getByTestId("scorecard-passed")).toHaveTextContent("1");
    expect(within(banner).getByTestId("scorecard-skipped")).toHaveTextContent("1");
    expect(within(banner).getByTestId("scorecard-detection")).toHaveTextContent("50%");
    for (const dim of ["identity", "capabilities", "policy", "behavior"]) {
      expect(within(banner).getByTestId(`scorecard-dim-${dim}`)).toHaveTextContent(
        "100%",
      );
    }
    expect(within(banner).getByTestId("scorecard-fp")).toHaveTextContent("1");
    expect(within(banner).getByTestId("scorecard-fn")).toHaveTextContent("0");
  });

  it("renders n/a for null dimension accuracies (captured dimension-less run)", async () => {
    mockLoaded(scorecardNa);

    renderPage();

    const banner = await screen.findByTestId("verdict-scorecard");
    expect(within(banner).getByTestId("scorecard-detection")).toHaveTextContent("100%");
    for (const dim of ["identity", "capabilities", "policy", "behavior"]) {
      expect(within(banner).getByTestId(`scorecard-dim-${dim}`)).toHaveTextContent(
        "n/a",
      );
    }
  });

  it("renders one row per judged entry with PASS/FAIL/SKIP chips", async () => {
    mockLoaded();

    renderPage();

    // PASS on the full-ground-truth agent.
    const passChip = (await rowOf("gt-full")).querySelector(".verdict-chip");
    expect(passChip).toHaveAttribute("data-status", "PASS");
    expect(passChip).toHaveTextContent("PASS");

    // FAIL variant 1: ground-truth mismatch (detected vs detectable false).
    const failChip = (await rowOf("gt-undetectable")).querySelector(".verdict-chip");
    expect(failChip).toHaveAttribute("data-status", "FAIL");

    // SKIP: agent without ground truth.
    const skipChip = (await rowOf("no-gt")).querySelector(".verdict-chip");
    expect(skipChip).toHaveAttribute("data-status", "SKIP");

    // FAIL variant 2: unknown agent, with the backend error surfaced.
    const ghostRow = await rowOf("ghost-agent");
    expect(ghostRow.querySelector(".verdict-chip")).toHaveAttribute(
      "data-status",
      "FAIL",
    );
    expect(within(ghostRow).getByText("unknown agent")).toBeInTheDocument();
  });

  it("expands a FAIL row to failed checks, expected vs observed and evidence links", async () => {
    mockLoaded();

    renderPage();

    fireEvent.click(await rowOf("gt-undetectable"));

    const detail = await screen.findByTestId("verdict-detail-gt-undetectable");
    // The single check of this entry failed.
    const failed = within(detail).getByTestId("failed-checks");
    expect(within(failed).getByText("detected")).toBeInTheDocument();
    // Expected vs observed side by side (captured payload contents).
    expect(within(detail).getByTestId("expected-json").textContent).toContain(
      '"detectable": false',
    );
    expect(within(detail).getByTestId("observed-json").textContent).toContain(
      '"detected": true',
    );
    // Evidence event ids deep-link to the audit page filtered on that event
    // (the audit page reads ?event_id= and shows an active-filter chip).
    const link = within(detail).getByRole("link", {
      name: "EV000000000000000001000001",
    });
    expect(link).toHaveAttribute(
      "href",
      "/audit?event_id=EV000000000000000001000001",
    );
  });

  it("shows the empty state with both submission paths when no verdicts exist", async () => {
    vi.mocked(getVerdicts).mockResolvedValue(null);
    vi.mocked(getVerdictScorecard).mockResolvedValue(null);

    renderPage();

    expect(await screen.findByText("No verdict submission yet")).toBeInTheDocument();
    // Way 1: HTTP hint with a curl one-liner against POST /verdicts.
    expect(screen.getByTestId("curl-hint").textContent).toContain("curl -X POST");
    expect(screen.getByTestId("curl-hint").textContent).toContain("/verdicts");
    // Way 2: the upload zone.
    expect(screen.getByLabelText("Upload results (.json)")).toBeInTheDocument();
  });

  it("uploads a valid results file and submits the parsed payload", async () => {
    vi.mocked(getVerdicts).mockResolvedValue(null);
    vi.mocked(getVerdictScorecard).mockResolvedValue(null);
    vi.mocked(postVerdicts).mockResolvedValue({
      judged: verdicts.judged,
      submitted_seq: verdicts.submitted_seq,
    });

    renderPage();
    await screen.findByText("No verdict submission yet");

    const payload = { tool: verdicts.tool, results: verdicts.results };
    const file = new File([JSON.stringify(payload)], "results.json", {
      type: "application/json",
    });
    fireEvent.change(screen.getByLabelText("Upload results (.json)"), {
      target: { files: [file] },
    });

    await waitFor(() => expect(postVerdicts).toHaveBeenCalledTimes(1));
    expect(vi.mocked(postVerdicts).mock.calls[0][0]).toEqual(payload);
    // A successful submission refreshes the banner and the table.
    await waitFor(() => expect(getVerdicts).toHaveBeenCalledTimes(2));
  });

  it("shows the parse error and does not submit on an invalid JSON file", async () => {
    vi.mocked(getVerdicts).mockResolvedValue(null);
    vi.mocked(getVerdictScorecard).mockResolvedValue(null);

    renderPage();
    await screen.findByText("No verdict submission yet");

    const file = new File(["{not json"], "broken.json", {
      type: "application/json",
    });
    fireEvent.change(screen.getByLabelText("Upload results (.json)"), {
      target: { files: [file] },
    });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(postVerdicts).not.toHaveBeenCalled();
  });
});
