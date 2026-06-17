import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DiscoveryPage from "./index";
import { getBenchmark, getDiscoveryCheck, getRecetteScorecard } from "../../api/client";
import type { Benchmark, DiscoveryCheck, RecetteScorecard } from "../../api/client";
import fixture from "./__fixtures__/scorecard.fixture.json";
import benchmarkFixture from "./__fixtures__/benchmark.fixture.json";
import checkFixture from "./__fixtures__/discovery-check.fixture.json";

vi.mock("../../api/client", () => ({
  getRecetteScorecard: vi.fn(),
  getBenchmark: vi.fn(),
  getDiscoveryCheck: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getBenchmark).mockResolvedValue(benchmarkFixture as Benchmark);
  vi.mocked(getDiscoveryCheck).mockResolvedValue(checkFixture as DiscoveryCheck);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("DiscoveryPage", () => {
  it("renders identification, maf and every discovery surface from a real payload", async () => {
    vi.mocked(getRecetteScorecard).mockResolvedValue(fixture as RecetteScorecard);
    render(<DiscoveryPage />);

    expect(await screen.findByTestId("discovery-verdict")).toHaveTextContent("PASS");
    // The multi-agent handoff orchestration area is surfaced.
    expect(screen.getByTestId("discovery-orchestration")).toHaveTextContent("orchestration 5/5");
    // The mcp surface (the feature under test) is present as its own row.
    const mcpRow = screen.getByTestId("discovery-row-mcp");
    expect(mcpRow).toBeInTheDocument();
    expect(mcpRow).toHaveTextContent("mcp");
    // Every captured surface renders a row.
    for (const surface of ["github", "gitlab", "temporal", "openapi", "mcp"]) {
      expect(screen.getByTestId(`discovery-row-${surface}`)).toBeInTheDocument();
    }
  });

  it("drills down to the per-repo discovery detail (GET /discovery/check)", async () => {
    vi.mocked(getRecetteScorecard).mockResolvedValue(fixture as RecetteScorecard);
    render(<DiscoveryPage />);

    // The drill-down panel renders, with the detection rate and a real repo row.
    expect(await screen.findByTestId("discovery-drill")).toBeInTheDocument();
    expect(screen.getByTestId("discovery-drill-rate")).toHaveTextContent("detection");
    expect(screen.getByTestId("discovery-repo-gh-pr-bot")).toBeInTheDocument();
  });

  it("shows an inline error when the fetch fails", async () => {
    vi.mocked(getRecetteScorecard).mockRejectedValue(new Error("boom"));
    render(<DiscoveryPage />);
    await waitFor(() =>
      expect(screen.getByTestId("discovery-error")).toHaveTextContent("boom"),
    );
  });
});
