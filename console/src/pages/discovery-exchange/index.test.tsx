/**
 * R16 contract test: the Discovery x Echange page renders the discovery verdict
 * overlaid on the real exchange against REAL backend payloads (produced by
 * recette/surface/exchange.py's serializer). Covers both discriminated states:
 * an identified exchange + a ghost exchange, a DETECTE agent + a GHOST agent.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import exchangeFixture from "./__fixtures__/exchange.fixture.json";
import ghostAgentFixture from "./__fixtures__/exchange-ghost-agent.fixture.json";
import type { AgentConfig, ExchangeReport } from "../../types/platform";

vi.mock("../../api/client", () => ({
  getDiscoveryExchange: vi.fn(),
  getProbeStatus: vi.fn(),
  captureProbe: vi.fn(),
  listAgents: vi.fn(),
  listCampaigns: vi.fn(),
  launchProcessRun: vi.fn(),
  processCapture: vi.fn(),
  processCaptureCampaign: vi.fn(),
  runCampaign: vi.fn(),
  getProbeMonitor: vi.fn(),
  startProbeMonitor: vi.fn(),
  stopProbeMonitor: vi.fn(),
}));

import {
  captureProbe,
  getDiscoveryExchange,
  getProbeMonitor,
  getProbeStatus,
  launchProcessRun,
  listAgents,
  listCampaigns,
  processCapture,
  processCaptureCampaign,
  startProbeMonitor,
} from "../../api/client";
import DiscoveryExchangePage from "./index";

const fixture = exchangeFixture as unknown as ExchangeReport;
const ghostFixture = ghostAgentFixture as unknown as ExchangeReport;
const probeOff = { configured: false, socket_env: "INSPECT_IA_AGENTS_PROBE_SOCKET", mode: "off" as const };

describe("DiscoveryExchangePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getProbeStatus).mockResolvedValue(probeOff);
    vi.mocked(listAgents).mockResolvedValue([]);
    vi.mocked(listCampaigns).mockResolvedValue([]);
    vi.mocked(getProbeMonitor).mockResolvedValue({
      running: false,
      window_ms: 2000,
      agents: [],
      windows: 0,
      last_error: null,
      sightings: [],
    });
  });

  it("starts the passive eBPF monitor and lists live sightings", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(fixture);
    vi.mocked(startProbeMonitor).mockResolvedValue({
      started: true,
      mode: "live",
      agents: ["dx-live-bot"],
    });
    vi.mocked(getProbeMonitor)
      .mockResolvedValueOnce({
        running: false,
        window_ms: 2000,
        agents: [],
        windows: 0,
        last_error: null,
        sightings: [],
      })
      .mockResolvedValue({
        running: true,
        window_ms: 2000,
        agents: ["dx-live-bot"],
        windows: 3,
        last_error: null,
        sightings: [
          { agent_id: "dx-live-bot", surfaces: ["ebpf_wire"], windows_seen: 2, last_window: 3 },
        ],
      });
    render(<DiscoveryExchangePage />);
    fireEvent.click(await screen.findByTestId("dx-monitor-toggle"));
    expect(await screen.findByTestId("sighting-dx-live-bot")).toHaveTextContent(/ebpf_wire/);
    expect(vi.mocked(startProbeMonitor)).toHaveBeenCalled();
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

  it("offers a run filter populated from the exchanges and narrows the view", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(fixture);
    render(<DiscoveryExchangePage />);
    const filter = (await screen.findByTestId("dx-run-filter")) as HTMLSelectElement;
    // the seeded run id is offered as an option
    expect(within(filter).getByRole("option", { name: /run-1/ })).toBeInTheDocument();
    // selecting it keeps the run-1 exchanges (all of the fixture)
    fireEvent.change(filter, { target: { value: "run-1" } });
    await waitFor(() =>
      expect(within(screen.getByTestId("exchange-table")).getAllByTestId("exchange-outcome").length)
        .toBeGreaterThan(0),
    );
  });

  it("captures via eBPF and surfaces a ghost AGENT from the broker scorecard", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(fixture);
    vi.mocked(getProbeStatus).mockResolvedValue({
      configured: true,
      socket_env: "INSPECT_IA_AGENTS_PROBE_SOCKET",
      mode: "replay",
    });
    vi.mocked(captureProbe).mockResolvedValue({
      recording: { status: "ok", recordings: [] },
      scorecard: {
        ok: false,
        total_agents: 2,
        detected_per_surface: { hook_sdk: 1 },
        false_negatives: ["shadow-agent"],
      },
    });
    render(<DiscoveryExchangePage />);
    // wait for the agents to load (so capture has agent ids), then switch source
    await screen.findByTestId("agent-pr-bot");
    fireEvent.click(screen.getByRole("button", { name: /eBPF/ }));
    const ghost = await screen.findByTestId("agent-shadow-agent");
    expect(within(ghost).getByTestId("agent-outcome")).toHaveTextContent("GHOST");
    expect(vi.mocked(captureProbe)).toHaveBeenCalled();
  });

  it("launches a process-mode (eBPF-observable) run from the picker", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(fixture);
    vi.mocked(listAgents).mockResolvedValue([
      { id: "proc-bot", runtime: "lab", ai_mode: "mock", scenario: [{ kind: "final", text: "x" }] },
    ] as AgentConfig[]);
    vi.mocked(launchProcessRun).mockResolvedValue({ run_id: "run-proc-123", status: "running" });
    render(<DiscoveryExchangePage />);

    const picker = (await screen.findByTestId("dx-proc-agent")) as HTMLSelectElement;
    await waitFor(() =>
      expect(within(picker).getByRole("option", { name: "proc-bot" })).toBeInTheDocument(),
    );
    fireEvent.change(picker, { target: { value: "proc-bot" } });
    fireEvent.click(screen.getByTestId("dx-launch-proc"));
    await waitFor(() =>
      expect(screen.getByTestId("dx-launch-msg")).toHaveTextContent(/process lance: proc-bot/),
    );
    expect(vi.mocked(launchProcessRun)).toHaveBeenCalledWith("proc-bot");
  });

  it("coordinates an eBPF capture with the process launch when the broker is live", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(fixture);
    vi.mocked(getProbeStatus).mockResolvedValue({
      configured: true,
      socket_env: "INSPECT_IA_AGENTS_PROBE_SOCKET",
      mode: "live",
    });
    vi.mocked(listAgents).mockResolvedValue([
      { id: "dx-live-bot", runtime: "lab", ai_mode: "mock", scenario: [{ kind: "final", text: "x" }] },
    ] as AgentConfig[]);
    vi.mocked(processCapture).mockResolvedValue({
      recording: { status: "ok", recordings: [] },
      scorecard: {
        ok: true,
        total_agents: 1,
        detected_per_surface: { ebpf_wire: 1 },
        false_negatives: [],
      },
    });
    render(<DiscoveryExchangePage />);
    const picker = await screen.findByTestId("dx-proc-agent");
    fireEvent.change(picker, { target: { value: "dx-live-bot" } });
    fireEvent.click(screen.getByTestId("dx-launch-proc"));
    // the kernel detection surfaces from the precise pid capture (process-capture)
    expect(await screen.findByTestId("ebpf-surface-ebpf_wire")).toHaveTextContent("DETECTE");
    expect(vi.mocked(processCapture)).toHaveBeenCalledWith("dx-live-bot");
  });

  it("captures a whole campaign via eBPF by pid from the campaign picker", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(fixture);
    vi.mocked(getProbeStatus).mockResolvedValue({
      configured: true,
      socket_env: "INSPECT_IA_AGENTS_PROBE_SOCKET",
      mode: "live",
    });
    vi.mocked(listCampaigns).mockResolvedValue([
      { id: "dx-live-camp", description: "live ebpf", steps: [{ agent_id: "dx-live-bot" }] },
    ]);
    vi.mocked(processCaptureCampaign).mockResolvedValue({
      recording: { status: "ok", recordings: [] },
      scorecard: {
        ok: true,
        total_agents: 1,
        detected_per_surface: { ebpf_wire: 1 },
        false_negatives: [],
      },
      agents: ["dx-live-bot"],
      skipped: [],
    });
    render(<DiscoveryExchangePage />);
    const picker = (await screen.findByTestId("dx-camp")) as HTMLSelectElement;
    await waitFor(() =>
      expect(within(picker).getByRole("option", { name: /dx-live-camp/ })).toBeInTheDocument(),
    );
    fireEvent.change(picker, { target: { value: "dx-live-camp" } });
    fireEvent.click(screen.getByTestId("dx-launch-camp"));
    expect(await screen.findByTestId("ebpf-surface-ebpf_wire")).toHaveTextContent("DETECTE");
    await waitFor(() =>
      expect(screen.getByTestId("dx-camp-msg")).toHaveTextContent(/campagne capturee: 1 agent/),
    );
    expect(vi.mocked(processCaptureCampaign)).toHaveBeenCalledWith("dx-live-camp");
  });

  it("renders named wire endpoints + an undeclared-host badge from the v1 annotation", async () => {
    vi.mocked(getDiscoveryExchange).mockResolvedValue(fixture);
    vi.mocked(getProbeStatus).mockResolvedValue({
      configured: true,
      socket_env: "INSPECT_IA_AGENTS_PROBE_SOCKET",
      mode: "live",
    });
    vi.mocked(listAgents).mockResolvedValue([
      { id: "dx-live-bot", runtime: "lab", ai_mode: "mock", scenario: [{ kind: "final", text: "x" }] },
    ] as AgentConfig[]);
    vi.mocked(processCapture).mockResolvedValue({
      recording: { status: "ok", recordings: [] },
      scorecard: {
        ok: true,
        total_agents: 2,
        detected_per_surface: { ebpf_wire: 1 },
        false_negatives: ["leak-bot"],
      },
      wire_named: {
        "dx-live-bot": [{ raw: "connect:127.0.0.1:9101", name: "gh-mock", undeclared: false }],
        "leak-bot": [{ raw: "connect:203.0.113.7:443", name: null, undeclared: true }],
      },
      undeclared_hosts: ["203.0.113.7:443"],
    });
    render(<DiscoveryExchangePage />);
    const picker = await screen.findByTestId("dx-proc-agent");
    fireEvent.change(picker, { target: { value: "dx-live-bot" } });
    fireEvent.click(screen.getByTestId("dx-launch-proc"));

    // the connect endpoint resolved to its declared server name
    const named = await screen.findByTestId("wire-agent-dx-live-bot");
    expect(within(named).getByText(/gh-mock \(127\.0\.0\.1:9101\)/)).toBeInTheDocument();
    // the undeclared endpoint carries the distinct badge
    expect(screen.getByTestId("wire-undeclared")).toHaveTextContent("host non declare");
    expect(vi.mocked(processCapture)).toHaveBeenCalledWith("dx-live-bot");
  });

  it("surfaces a load error without crashing", async () => {
    vi.mocked(getDiscoveryExchange).mockRejectedValue(new Error("exchange down"));
    render(<DiscoveryExchangePage />);
    await waitFor(() => expect(screen.getByText(/exchange down/)).toBeInTheDocument());
  });
});
