/**
 * WS-C R16 contract gate: the observability span-tree renders against a REAL
 * captured payload (fixtures dumped from GET /observability/traces[/:id]).
 * Asserts the legibility-first fields a third party needs: the action (tool),
 * the resource, the access mode and the approval state (I6).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

vi.mock("../../components/help/PageHelp", () => ({
  default: () => null,
}));

import { getObservabilityTrace, listObservabilityTraces } from "../../api/client";
import ObservabilityPage from "./index";

const traces = tracesFixture as unknown as ObservabilityTraceSummary[];
const trace = traceFixture as unknown as ObservabilityTrace;

/** Read a span attribute from the fixture for assertion (real payload, R16). */
function spanAttr(index: number, key: string): string {
  const v = trace.spans[index].attributes[key];
  return v === undefined ? "" : String(v);
}

describe("ObservabilityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists traces and renders a legible span tree on selection (R16)", async () => {
    vi.mocked(listObservabilityTraces).mockResolvedValue(traces);
    vi.mocked(getObservabilityTrace).mockResolvedValue(trace);

    render(
      <MemoryRouter>
        <ObservabilityPage />
      </MemoryRouter>,
    );

    const row = await screen.findByText(traces[0].agent_id ?? traces[0].recording_id);
    fireEvent.click(row);

    await waitFor(() => {
      expect(getObservabilityTrace).toHaveBeenCalledWith(traces[0].trace_id);
    });

    // Each tool span surfaces the action (tool name), not just the raw span name.
    const tool1 = spanAttr(1, "gen_ai.tool.name");
    expect(await screen.findByText(tool1)).toBeInTheDocument();

    // And the resource the action touched (legibility-first: what it asked).
    const resource = spanAttr(1, "inspect_ia_agents.resource");
    if (resource) expect(screen.getAllByText(resource).length).toBeGreaterThan(0);

    // A write action that was not approved shows the I6 state explicitly.
    const writeSpan = trace.spans.find(
      (s) => String(s.attributes["inspect_ia_agents.mode"]) === "write",
    );
    if (writeSpan) {
      const approved = Number(writeSpan.attributes["inspect_ia_agents.approved"]) === 1;
      expect(screen.getAllByText(approved ? "approuve" : "non approuve").length).toBeGreaterThan(0);
    }

    // The derived run summary gives visibility at a glance (counts + I6 risk).
    const stats = await screen.findByTestId("obs-stats");
    const toolCount = trace.spans.filter(
      (s) => String(s.attributes["gen_ai.operation.name"]) === "execute_tool",
    ).length;
    expect(stats).toHaveTextContent(`${toolCount} action(s)`);

    // Expanding a span reveals its FULL attribute set (deep per-step visibility).
    const hiddenKey = "gen_ai.tool.call.id";
    expect(screen.queryByText(hiddenKey)).toBeNull(); // collapsed by default
    fireEvent.click(screen.getByText(tool1)); // click the tool span line
    expect(await screen.findByText(hiddenKey)).toBeInTheDocument();
  });

  it("filters the trace list by agent/target/recording (R16)", async () => {
    vi.mocked(listObservabilityTraces).mockResolvedValue(traces);
    render(
      <MemoryRouter>
        <ObservabilityPage />
      </MemoryRouter>,
    );

    // All traces visible at first.
    const firstAgent = traces[0].agent_id ?? traces[0].recording_id;
    await screen.findByText(firstAgent);

    // Filtering by a string absent from every trace empties the list.
    fireEvent.change(screen.getByTestId("obs-filter"), {
      target: { value: "zzz-no-such-agent-zzz" },
    });
    expect(await screen.findByTestId("obs-no-match")).toBeInTheDocument();
    expect(screen.queryByText(firstAgent)).toBeNull();
  });

  it("shows an empty state with a link to the cockpit before any run", async () => {
    vi.mocked(listObservabilityTraces).mockResolvedValue([]);
    render(
      <MemoryRouter>
        <ObservabilityPage />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("obs-empty")).toBeInTheDocument();
    const link = screen.getByTestId("obs-empty-cockpit-link");
    expect(link).toHaveAttribute("href", "/cockpit");
  });
});
