import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CorpusPage from "./index";
import { listSubjects } from "../../api/client";
import type { CorpusListing } from "../../api/client";
import fixture from "./__fixtures__/subjects.fixture.json";

vi.mock("../../api/client", () => ({
  listSubjects: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("CorpusPage", () => {
  it("lists subjects across families from a real payload", async () => {
    vi.mocked(listSubjects).mockResolvedValue(fixture as CorpusListing);
    render(<CorpusPage />);

    expect(await screen.findByTestId("corpus-count")).toHaveTextContent("24 subjects");
    // Every family has a filter chip with its count.
    expect(screen.getByTestId("corpus-filter-git_agent")).toHaveTextContent("git_agent 10");
    expect(screen.getByTestId("corpus-filter-maf_agent")).toHaveTextContent("maf_agent 5");
    expect(screen.getByTestId("corpus-filter-maf_orchestration")).toHaveTextContent(
      "maf_orchestration 9",
    );
    // An orchestration team surfaces with its broken axis.
    const row = screen.getByTestId("corpus-row-support-handoff-capability-overreach");
    expect(row).toHaveTextContent("maf_orchestration");
    expect(row).toHaveTextContent("capability_overreach");
    expect(row).toHaveTextContent("incorrect");
  });

  it("filters to a single family on chip click", async () => {
    vi.mocked(listSubjects).mockResolvedValue(fixture as CorpusListing);
    render(<CorpusPage />);
    await screen.findByTestId("corpus-count");

    fireEvent.click(screen.getByTestId("corpus-filter-maf_orchestration"));
    // git rows disappear, orchestration rows remain.
    expect(screen.queryByTestId("corpus-row-support-handoff-correct")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryAllByTestId(/corpus-row-/).every((r) =>
          r.textContent?.includes("maf_orchestration"),
        ),
      ).toBe(true),
    );
  });

  it("shows an inline error when the fetch fails", async () => {
    vi.mocked(listSubjects).mockRejectedValue(new Error("boom"));
    render(<CorpusPage />);
    await waitFor(() => expect(screen.getByTestId("corpus-error")).toHaveTextContent("boom"));
  });
});
