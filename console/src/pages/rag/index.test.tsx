import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RagPage from "./index";
import { getRagScorecard } from "../../api/client";
import fixture from "./__fixtures__/ragScorecard.fixture.json";
import type { RagScorecard } from "../../types/platform";

vi.mock("../../api/client", () => ({
  getRagScorecard: vi.fn(),
  // RagPage now embeds the KnowledgeBaseManager; stub its calls so these
  // scorecard tests stay focused (the manager has its own test file).
  listKbDocuments: vi.fn(() => Promise.resolve([])),
  listRagScenarios: vi.fn(() => Promise.resolve([])),
  resetKb: vi.fn(),
  applyRagScenario: vi.fn(),
  addKbDocument: vi.fn(),
  deleteKbDocument: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("RagPage", () => {
  it("renders the scorecard summary and one row per query from a real payload", async () => {
    vi.mocked(getRagScorecard).mockResolvedValue(fixture as RagScorecard);
    render(<RagPage />);

    // Aggregate verdict + per-query rows from the captured fixture.
    expect(await screen.findByTestId("rag-verdict")).toHaveTextContent("PASS");
    expect(screen.getByText("3/3 queries")).toBeInTheDocument();
    expect(screen.getByText("mean precision 0.67")).toBeInTheDocument();
    expect(screen.getByText("mean recall 1.00")).toBeInTheDocument();

    const rows = screen.getAllByTestId("rag-row");
    expect(rows).toHaveLength(3);
    expect(
      screen.getByText("approval before deleting documents"),
    ).toBeInTheDocument();
    // The retrieved doc ids render as a joined list.
    expect(screen.getByText("kb-approval, kb-ranking")).toBeInTheDocument();
  });

  it("shows an inline error when the fetch fails", async () => {
    vi.mocked(getRagScorecard).mockRejectedValue(new Error("boom"));
    render(<RagPage />);
    await waitFor(() =>
      expect(screen.getByTestId("rag-error")).toHaveTextContent("boom"),
    );
  });

  it("renders an empty state when the ground-truth set has no queries", async () => {
    vi.mocked(getRagScorecard).mockResolvedValue({
      total: 0,
      passed: 0,
      all_passed: false,
      mean_precision: 0,
      mean_recall: 0,
      results: [],
    });
    render(<RagPage />);
    expect(
      await screen.findByText("No queries in the ground-truth set."),
    ).toBeInTheDocument();
  });
});
