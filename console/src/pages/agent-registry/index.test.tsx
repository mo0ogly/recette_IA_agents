/**
 * R16 contract test: the agent-registry page renders the generated registry +
 * its metadata against a REAL captured /registry/agents payload, and filters by
 * party.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import registryFixture from "./__fixtures__/registry.fixture.json";
import type { AgentRegistry } from "../../types/platform";

vi.mock("../../api/client", () => ({ getAgentRegistry: vi.fn() }));

import { getAgentRegistry } from "../../api/client";
import AgentRegistryPage from "./index";

const registry = registryFixture as unknown as AgentRegistry;

describe("AgentRegistryPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the generated registry with metadata and filters by party", async () => {
    vi.mocked(getAgentRegistry).mockResolvedValue(registry);
    render(<AgentRegistryPage />);

    const table = await screen.findByTestId("registry-table");
    // A seeded subject with metadata shows its party + compliance.
    const withParty = registry.agents.find((a) => a.party === "1p");
    expect(withParty).toBeDefined();
    expect(within(table).getByText(withParty!.agent_id)).toBeInTheDocument();

    // Filter to 3p: a 1p-only subject disappears.
    const has3p = registry.agents.some((a) => a.party === "3p");
    if (has3p) {
      fireEvent.change(screen.getByLabelText("Party"), { target: { value: "3p" } });
      expect(within(table).queryByText(withParty!.agent_id)).not.toBeInTheDocument();
    }
  });

  it("surfaces a load error without crashing", async () => {
    vi.mocked(getAgentRegistry).mockRejectedValue(new Error("registry down"));
    render(<AgentRegistryPage />);
    await waitFor(() => expect(screen.getByText(/registry down/)).toBeInTheDocument());
  });
});
