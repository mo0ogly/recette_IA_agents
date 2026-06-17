/**
 * WS-C R16 contract gate: the observability span-tree renders against a REAL
 * captured payload (fixtures dumped from GET /observability/traces[/:id]).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import tracesFixture from "./__fixtures__/traces.fixture.json";
import traceFixture from "./__fixtures__/trace.fixture.json";
import type {
  ObservabilityTrace,
  ObservabilityTraceSummary,
} from "../../types/platform";

vi.mock("../../api/client", () => ({
  listObservabilityTraces: vi.fn(),
  getObservabilityTrace: vi.fn(),
}));

import { getObservabilityTrace, listObservabilityTraces } from "../../api/client";
import ObservabilityPage from "./index";

const traces = tracesFixture as unknown as ObservabilityTraceSummary[];
const trace = traceFixture as unknown as ObservabilityTrace;

describe("ObservabilityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists traces and renders the span tree on selection (R16)", async () => {
    vi.mocked(listObservabilityTraces).mockResolvedValue(traces);
    vi.mocked(getObservabilityTrace).mockResolvedValue(trace);

    render(<ObservabilityPage />);

    // Trace row from the real payload (agent id + span count).
    const row = await screen.findByText(traces[0].agent_id ?? traces[0].recording_id);
    fireEvent.click(row);

    // The detail is fetched for the selected trace id and the spans render.
    await waitFor(() => {
      expect(getObservabilityTrace).toHaveBeenCalledWith(traces[0].trace_id);
    });
    // Root invoke_agent span + one execute_tool span per action.
    expect(await screen.findByText(trace.spans[0].name)).toBeInTheDocument();
    expect(screen.getByText(trace.spans[1].name)).toBeInTheDocument();
  });

  it("shows an empty state before any run", async () => {
    vi.mocked(listObservabilityTraces).mockResolvedValue([]);
    render(<ObservabilityPage />);
    expect(await screen.findByText(/Aucune trace/)).toBeInTheDocument();
  });
});
