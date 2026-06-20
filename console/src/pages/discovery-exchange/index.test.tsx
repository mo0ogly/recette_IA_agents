/**
 * R16 contract test: the Discovery x Echange page renders the discovery verdict
 * overlaid on the real exchange against REAL backend payloads (produced by
 * recette/surface/exchange.py's serializer). Covers both discriminated states:
 * an identified exchange + a ghost exchange, a DETECTE agent + a GHOST agent.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import exchangeFixture from "./__fixtures__/exchange.fixture.json";
import ghostAgentFixture from "./__fixtures__/exchange-ghost-agent.fixture.json";
import type { ExchangeReport } from "../../types/platform";

vi.mock("../../api/client", () => ({
  getDiscoveryExchange: vi.fn(),
  getProbeStatus: vi.fn(),
  captureProbe: vi.fn(),
}));

import { getDiscoveryExchange, getProbeStatus } from "../../api/client";
import DiscoveryExchangePage from "./index";

const fixture = exchangeFixture as unknown as ExchangeReport;
const ghostFixture = ghostAgentFixture as unknown as ExchangeReport;
const probeOff = { configured: false, socket_env: "INSPECT_IA_AGENTS_PROBE_SOCKET", mode: "off" as const };

describe("DiscoveryExchangePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getProbeStatus).mockResolvedValue(probeOff);
  });

  it("renders the real exchange with identified + ghost verdicts and the ghost count", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(fixture);
    render(<DiscoveryExchangePage />);

    const table = await screen.findByTestId("exchange-table");
    // a hook exchange is identified, the wire-only flow is a ghost exchange
    expect(within(table).getByText(/open_pr github\/octo\/repo/)).toBeInTheDocument();
    expect(within(table).getByText(/evil\.test:443\/leak \(non_mediated_target\)/)).toBeInTheDocument();
    const outcomes = within(table).getAllByTestId("exchange-outcome").map((n) => n.textContent);
    expect(outcomes).toContain("identifie");
    expect(outcomes).toContain("ghost");
    // the run-level ghost-exchange signal
    expect(screen.getByTestId("dx-ghost-count")).toHaveTextContent("1 echange(s) ghost");
    // both agents are DETECTE on the hook surfaces
    expect(within(screen.getByTestId("agent-pr-bot")).getByTestId("agent-outcome")).toHaveTextContent(
      "DETECTE",
    );
  });

  it("renders a GHOST agent (detected on no surface) from the eBPF-sourced shape", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(ghostFixture);
    render(<DiscoveryExchangePage />);

    const ghost = await screen.findByTestId("agent-shadow-agent");
    expect(within(ghost).getByTestId("agent-outcome")).toHaveTextContent("GHOST");
    expect(within(ghost).getByText(/aucune surface/)).toBeInTheDocument();
    expect(screen.getByTestId("scorecard")).toHaveTextContent(/1 ghost/);
  });

  it("surfaces a load error without crashing", async () => {
    vi.mocked(getDiscoveryExchange).mockRejectedValue(new Error("exchange down"));
    render(<DiscoveryExchangePage />);
    await waitFor(() => expect(screen.getByText(/exchange down/)).toBeInTheDocument());
  });
});
