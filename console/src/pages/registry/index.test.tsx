/**
 * R16 contract tests for the agent catalog registry page.
 *
 * The fixture (__fixtures__/catalog-summary.fixture.json) is the captured raw
 * GET /catalog/summary payload (no envelope -- the endpoint answers raw, exactly
 * what getCatalogSummary resolves with), so the render-and-assert proves the page
 * consumes the live contract shape without crashing.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegistryPage from "./index";
import { getCatalogSummary } from "../../api/client";
import type { CatalogSummary } from "../../types/platform";
import fixture from "./__fixtures__/catalog-summary.fixture.json";

vi.mock("../../api/client", () => ({
  getCatalogSummary: vi.fn(),
}));

// The endpoint answers raw; the test feeds the mock the captured raw payload.
const payload = fixture as unknown as CatalogSummary;

afterEach(() => {
  vi.clearAllMocks();
});

describe("RegistryPage", () => {
  it("renders the summary counts, every agent and marks a tool-less agent", async () => {
    vi.mocked(getCatalogSummary).mockResolvedValue(payload);
    render(<RegistryPage />);

    // Summary counts (total / with_tools) render.
    expect(await screen.findByTestId("registry-total")).toHaveTextContent("5");
    expect(screen.getByTestId("registry-with-tools")).toHaveTextContent("4");

    // Every agent name renders.
    expect(screen.getByTestId("registry-agent-github-pr-bot")).toBeInTheDocument();
    expect(screen.getByTestId("registry-agent-okta-provisioner")).toBeInTheDocument();
    expect(screen.getByTestId("registry-agent-finance-reconciler")).toBeInTheDocument();
    expect(screen.getByTestId("registry-agent-support-triage")).toBeInTheDocument();
    expect(screen.getByTestId("registry-agent-silent-scanner")).toBeInTheDocument();

    // A normal agent shows its tool count.
    expect(screen.getByTestId("registry-agent-tools-github-pr-bot")).toHaveTextContent(
      "2 outils",
    );

    // The silent agent (tool_count 0) is shown distinctly.
    const silent = screen.getByTestId("registry-agent-silent-scanner");
    expect(silent).toHaveClass("registry-agent-silent");
    expect(screen.getByTestId("registry-agent-tools-silent-scanner")).toHaveTextContent(
      "aucun outil",
    );

    // The deduplicated tag union is rendered.
    expect(screen.getByTestId("registry-tag-union")).toHaveTextContent("github");
  });

  it("renders an empty state for a registry with no agents (no crash)", async () => {
    const empty: CatalogSummary = {
      version: "1.0",
      summary: { total: 0, unique: 0, with_tools: 0, tags: [] },
      agents: [],
    };
    vi.mocked(getCatalogSummary).mockResolvedValue(empty);
    render(<RegistryPage />);

    expect(await screen.findByTestId("registry-empty")).toBeInTheDocument();
    expect(screen.getByTestId("registry-total")).toHaveTextContent("0");
    expect(screen.queryByTestId("registry-agents")).not.toBeInTheDocument();
  });

  it("surfaces a fetch error inline (fail-safe)", async () => {
    vi.mocked(getCatalogSummary).mockRejectedValue(new Error("503 catalog unavailable"));
    render(<RegistryPage />);

    await waitFor(() =>
      expect(screen.getByTestId("registry-error")).toHaveTextContent(
        "503 catalog unavailable",
      ),
    );
  });
});
