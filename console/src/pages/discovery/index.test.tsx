import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DiscoveryPage from "./index";
import { getRecetteScorecard } from "../../api/client";
import type { RecetteScorecard } from "../../api/client";
import fixture from "./__fixtures__/scorecard.fixture.json";

vi.mock("../../api/client", () => ({
  getRecetteScorecard: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("DiscoveryPage", () => {
  it("renders identification, maf and every discovery surface from a real payload", async () => {
    vi.mocked(getRecetteScorecard).mockResolvedValue(fixture as RecetteScorecard);
    render(<DiscoveryPage />);

    expect(await screen.findByTestId("discovery-verdict")).toHaveTextContent("PASS");
    // The mcp surface (the feature under test) is present as its own row.
    const mcpRow = screen.getByTestId("discovery-row-mcp");
    expect(mcpRow).toBeInTheDocument();
    expect(mcpRow).toHaveTextContent("mcp");
    // Every captured surface renders a row.
    for (const surface of ["github", "gitlab", "temporal", "openapi", "mcp"]) {
      expect(screen.getByTestId(`discovery-row-${surface}`)).toBeInTheDocument();
    }
  });

  it("shows an inline error when the fetch fails", async () => {
    vi.mocked(getRecetteScorecard).mockRejectedValue(new Error("boom"));
    render(<DiscoveryPage />);
    await waitFor(() =>
      expect(screen.getByTestId("discovery-error")).toHaveTextContent("boom"),
    );
  });
});
