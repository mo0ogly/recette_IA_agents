/**
 * R16 contract test: the interaction-graph page renders the directed graph +
 * the per-node metrics table against a REAL captured /graph payload.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import graphFixture from "./__fixtures__/graph.fixture.json";
import type { OrchestrationGraph } from "../../types/platform";

vi.mock("../../api/client", () => ({
  listSubjects: vi.fn(),
  getOrchestrationGraph: vi.fn(),
}));

import { getOrchestrationGraph, listSubjects } from "../../api/client";
import GraphPage from "./index";

const fixture = graphFixture as unknown as { agent_id: string; graph: OrchestrationGraph };

describe("GraphPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the directed graph + per-node metrics from the real payload", async () => {
    vi.mocked(listSubjects).mockResolvedValue({
      count: 1,
      families: {},
      subjects: [
        {
          agent_id: fixture.agent_id,
          name: fixture.agent_id,
          family: "maf_orchestration",
          target_systems: [],
          manifest_file: "team.json",
          category: null,
          violation_type: null,
          expected_verdict: null,
        },
      ],
    } as never);
    vi.mocked(getOrchestrationGraph).mockResolvedValue(fixture.graph);

    render(<GraphPage />);

    await waitFor(() =>
      expect(getOrchestrationGraph).toHaveBeenCalledWith(fixture.agent_id),
    );

    // The per-node metrics table renders one row per participant.
    const table = await screen.findByTestId("graph-metrics");
    const firstNode = fixture.graph.nodes[0].id;
    expect(within(table).getByText(firstNode)).toBeInTheDocument();

    // The mermaid diagram source carries a weighted handoff edge.
    if (fixture.graph.edges.length > 0) {
      const e = fixture.graph.edges[0];
      expect(screen.getByText(new RegExp(`${e.source} -->`))).toBeInTheDocument();
    }
  });

  it("surfaces a load error without crashing", async () => {
    vi.mocked(listSubjects).mockRejectedValue(new Error("subjects down"));
    render(<GraphPage />);
    await waitFor(() => expect(screen.getByText(/subjects down/)).toBeInTheDocument());
  });
});
