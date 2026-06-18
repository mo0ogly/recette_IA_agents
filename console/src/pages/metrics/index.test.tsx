/**
 * R16 contract test: the Metrics page renders per-agent + per-tool tables
 * against a REAL captured /metrics/summary payload.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import summaryFixture from "./__fixtures__/summary.fixture.json";
import type { MetricsSummary } from "../../types/platform";

vi.mock("../../api/client", () => ({ getMetricsSummary: vi.fn() }));

import { getMetricsSummary } from "../../api/client";
import MetricsPage from "./index";

const summary = summaryFixture as unknown as MetricsSummary;

describe("MetricsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the per-agent and per-tool metric tables from the real payload", async () => {
    vi.mocked(getMetricsSummary).mockResolvedValue(summary);
    render(<MetricsPage />);

    const agents = await screen.findByTestId("metrics-agents");
    const firstAgent = Object.keys(summary.agents)[0];
    expect(within(agents).getByText(firstAgent)).toBeInTheDocument();

    const tools = screen.getByTestId("metrics-tools");
    const firstTool = Object.keys(summary.tools)[0];
    expect(within(tools).getByText(firstTool)).toBeInTheDocument();

    // Totals strip surfaces the call count.
    expect(
      within(screen.getByTestId("metrics-totals")).getByText(
        new RegExp(`${summary.totals.calls} appel`),
      ),
    ).toBeInTheDocument();
  });

  it("surfaces a load error without crashing", async () => {
    vi.mocked(getMetricsSummary).mockRejectedValue(new Error("metrics down"));
    render(<MetricsPage />);
    await waitFor(() => expect(screen.getByText(/metrics down/)).toBeInTheDocument());
  });
});
