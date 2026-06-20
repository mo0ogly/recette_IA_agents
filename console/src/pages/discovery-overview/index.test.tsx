/**
 * R16 contract tests for the unified Discovery dashboard.
 *
 * The fixture (__fixtures__/discovery-overview.fixture.json) is the captured RAW
 * GET /discovery/overview payload (no envelope -- the endpoint answers raw,
 * exactly what getDiscoveryOverview resolves with), so the render-and-assert
 * proves the page consumes the live contract shape without crashing. The page
 * renders <Link>s, so each render is wrapped in a MemoryRouter.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import DiscoveryPage from "./index";
import { getDiscoveryOverview } from "../../api/client";
import type { DiscoveryOverview } from "../../types/platform";
import fixture from "./__fixtures__/discovery-overview.fixture.json";

vi.mock("../../api/client", () => ({
  getDiscoveryOverview: vi.fn(),
}));

// The endpoint answers raw; the test feeds the mock the captured raw payload.
const payload = fixture as unknown as DiscoveryOverview;

function renderPage(): void {
  render(
    <MemoryRouter>
      <DiscoveryPage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("DiscoveryPage (overview)", () => {
  it("renders the catalog stats, the reperage tally and the governance axis", async () => {
    vi.mocked(getDiscoveryOverview).mockResolvedValue(payload);
    renderPage();

    // Catalog: total agents (5) and with-tools (4) render.
    expect(
      await screen.findByTestId("discovery-overview-catalog-total-value"),
    ).toHaveTextContent("5");
    expect(
      screen.getByTestId("discovery-overview-catalog-with-tools-value"),
    ).toHaveTextContent("4");
    expect(
      screen.getByTestId("discovery-overview-catalog-tags-value"),
    ).toHaveTextContent("9");

    // Catalog links to the existing /registry page.
    expect(screen.getByTestId("discovery-overview-catalog-link")).toHaveAttribute(
      "href",
      "/registry",
    );

    // Reperage: tool count (12) renders.
    expect(
      screen.getByTestId("discovery-overview-detect-tools-value"),
    ).toHaveTextContent("12");

    // Reperage links to the existing /detect page.
    expect(screen.getByTestId("discovery-overview-detect-link")).toHaveAttribute(
      "href",
      "/detect",
    );

    // Category distribution is rendered (by_category).
    expect(
      screen.getByTestId("discovery-overview-category-tracing"),
    ).toHaveTextContent("10");

    // Capability distribution makes the GOVERNANCE axis visible: audit (3) and
    // replay (2) both render, marked as governance.
    const audit = screen.getByTestId("discovery-overview-capability-audit");
    expect(audit).toHaveTextContent("3");
    expect(audit).toHaveClass("discovery-overview-dist-row-governance");
    expect(screen.getByTestId("discovery-overview-gov-audit")).toBeInTheDocument();

    const replay = screen.getByTestId("discovery-overview-capability-replay");
    expect(replay).toHaveTextContent("2");
    expect(replay).toHaveClass("discovery-overview-dist-row-governance");
    expect(screen.getByTestId("discovery-overview-gov-replay")).toBeInTheDocument();
  });

  it("renders an empty state for an all-zero overview (no crash)", async () => {
    const empty: DiscoveryOverview = {
      catalog: { total: 0, with_tools: 0, tags: 0 },
      detect: { tools: 0, by_category: {}, by_capability: {} },
    };
    vi.mocked(getDiscoveryOverview).mockResolvedValue(empty);
    renderPage();

    expect(
      await screen.findByTestId("discovery-overview-empty"),
    ).toBeInTheDocument();
    // The stat cards still render, at zero -- no crash.
    expect(
      screen.getByTestId("discovery-overview-catalog-total-value"),
    ).toHaveTextContent("0");
    expect(
      screen.getByTestId("discovery-overview-detect-tools-value"),
    ).toHaveTextContent("0");
  });

  it("surfaces a fetch error inline (fail-safe)", async () => {
    vi.mocked(getDiscoveryOverview).mockRejectedValue(
      new Error("503 discovery unavailable"),
    );
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("discovery-overview-error")).toHaveTextContent(
        "503 discovery unavailable",
      ),
    );
  });
});
