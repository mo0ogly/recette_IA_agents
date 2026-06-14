/**
 * Tests for the Cockpit page network log.
 *
 * The cockpit is a per-agent debug view. Its bottom panel shows the side-effect
 * PROXY traces (I5) for the active run -- what the agent actually sent to its
 * target system -- not the governed audit log (lane_b runs never reach it).
 *
 * traces.fixture.json was captured from a live GET /proxy/traces; the test
 * drives the launch flow and asserts the panel polls the traces for the new
 * run_id and renders them (R16: real payload, render-and-assert).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import agentsFixture from "../agents/__fixtures__/agents.fixture.json";
import backendsFixture from "../agents/__fixtures__/ai-backends.fixture.json";
import tracesFixture from "../proxy/__fixtures__/traces.fixture.json";
import type {
  AgentConfig,
  AiBackend,
  ProxyTraceResponse,
} from "../../types/platform";

// The lazy Monaco viewer is stubbed (Monaco needs a real DOM/workers); the stub
// surfaces its `value` so the test can assert the exchange JSON is shown.
vi.mock("../../components/MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => (
    <textarea readOnly data-testid="monaco-stub" value={value} />
  ),
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listAgents: vi.fn(),
    listAiBackends: vi.fn(),
    launchLaneB: vi.fn(),
    openRunSocket: vi.fn(),
    stopRun: vi.fn(),
    getProxyTraces: vi.fn(),
  };
});

import {
  getProxyTraces,
  launchLaneB,
  listAgents,
  listAiBackends,
  openRunSocket,
} from "../../api/client";
import CockpitPage from "./index";

const traces = tracesFixture as ProxyTraceResponse;

describe("CockpitPage network log", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty network log before any run, without polling traces", async () => {
    vi.mocked(listAgents).mockResolvedValue([]);
    vi.mocked(listAiBackends).mockResolvedValue([]);
    vi.mocked(getProxyTraces).mockResolvedValue({ debug_enabled: true, traces: [] });

    render(<CockpitPage />);

    expect(
      await screen.findByText("Logs reseau (lance l'agent pour tracer ses appels)"),
    ).toBeInTheDocument();
    // No run yet -> the panel does not poll the proxy.
    expect(getProxyTraces).not.toHaveBeenCalled();
  });

  it("tails the proxy network log for the launched run", async () => {
    vi.mocked(listAgents).mockResolvedValue(agentsFixture as AgentConfig[]);
    vi.mocked(listAiBackends).mockResolvedValue(backendsFixture as AiBackend[]);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "RID123", status: "pending" });
    // The cockpit wires handlers onto the returned socket; a plain object is enough.
    vi.mocked(openRunSocket).mockReturnValue({
      onmessage: null,
      onopen: null,
      onerror: null,
      close: vi.fn(),
    } as unknown as WebSocket);
    vi.mocked(getProxyTraces).mockResolvedValue(traces);

    render(<CockpitPage />);

    // The picker is populated from the fixture; launch the selected agent.
    await screen.findByText(/gh-pr-bot/);
    fireEvent.click(screen.getByRole("button", { name: "Lancer" }));

    // The panel polls the proxy traces for the new run id and renders them.
    await waitFor(() => {
      expect(getProxyTraces).toHaveBeenCalledWith(200, "RID123");
    });
    const first = traces.traces[0];
    const label = `${first.action_type} ${first.target_system}/${first.resource} -> ${first.status_code}`;
    expect((await screen.findAllByText(label)).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Logs reseau -- run RID123").length).toBeGreaterThan(0);
  });

  it("opens the agent <-> server exchange (request + response) on a trace click", async () => {
    vi.mocked(listAgents).mockResolvedValue(agentsFixture as AgentConfig[]);
    vi.mocked(listAiBackends).mockResolvedValue(backendsFixture as AiBackend[]);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "RID123", status: "pending" });
    vi.mocked(openRunSocket).mockReturnValue({
      onmessage: null,
      onopen: null,
      onerror: null,
      close: vi.fn(),
    } as unknown as WebSocket);
    vi.mocked(getProxyTraces).mockResolvedValue(traces);

    render(<CockpitPage />);
    await screen.findByText(/gh-pr-bot/);
    fireEvent.click(screen.getByRole("button", { name: "Lancer" }));

    const first = traces.traces[0];
    const label = `${first.action_type} ${first.target_system}/${first.resource} -> ${first.status_code}`;
    const line = (await screen.findAllByText(label))[0];
    fireEvent.click(line);

    // The exchange panel shows both halves; the server response body is what was
    // missing before -- assert one of its values reaches the (stubbed) viewer.
    const viewer = await screen.findByTestId("monaco-stub");
    // Request side carries the agent's intent (action_type + resource), not just
    // the usually-empty payload; response side carries the server body.
    expect((viewer as HTMLTextAreaElement).value).toContain("action_type");
    expect((viewer as HTMLTextAreaElement).value).toContain("response");
    expect((viewer as HTMLTextAreaElement).value).toContain(
      String((first.response as { result_id: string }).result_id),
    );
  });

  it("exposes Tous + the run's agent and server in the log filters", async () => {
    vi.mocked(listAgents).mockResolvedValue(agentsFixture as AgentConfig[]);
    vi.mocked(listAiBackends).mockResolvedValue(backendsFixture as AiBackend[]);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "RID123", status: "pending" });
    vi.mocked(openRunSocket).mockReturnValue({
      onmessage: null,
      onopen: null,
      onerror: null,
      close: vi.fn(),
    } as unknown as WebSocket);
    vi.mocked(getProxyTraces).mockResolvedValue(traces);

    render(<CockpitPage />);
    await screen.findByText(/gh-pr-bot/);
    fireEvent.click(screen.getByRole("button", { name: "Lancer" }));

    // Filter options are derived from the run's traces (agent_id / target_system).
    const first = traces.traces[0];
    expect(await screen.findByRole("option", { name: first.agent_id })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: first.target_system })).toBeInTheDocument();
    // Each filter select offers the "Tous" (no-filter) default.
    expect(screen.getAllByRole("option", { name: "Tous" }).length).toBe(2);
  });

  it("filters the exchange to request-only or response-only", async () => {
    vi.mocked(listAgents).mockResolvedValue(agentsFixture as AgentConfig[]);
    vi.mocked(listAiBackends).mockResolvedValue(backendsFixture as AiBackend[]);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "RID123", status: "pending" });
    vi.mocked(openRunSocket).mockReturnValue({
      onmessage: null,
      onopen: null,
      onerror: null,
      close: vi.fn(),
    } as unknown as WebSocket);
    vi.mocked(getProxyTraces).mockResolvedValue(traces);

    render(<CockpitPage />);
    await screen.findByText(/gh-pr-bot/);
    fireEvent.click(screen.getByRole("button", { name: "Lancer" }));

    // The exchange auto-shows; the direction select narrows it.
    const viewer = await screen.findByTestId("monaco-stub");
    const select = screen.getByRole("combobox", { name: "Afficher" });

    fireEvent.change(select, { target: { value: "response" } });
    expect((viewer as HTMLTextAreaElement).value).toContain("response");
    expect((viewer as HTMLTextAreaElement).value).not.toContain('"request"');

    fireEvent.change(select, { target: { value: "request" } });
    expect((viewer as HTMLTextAreaElement).value).toContain("action_type");
    expect((viewer as HTMLTextAreaElement).value).not.toContain('"response"');
  });
});
