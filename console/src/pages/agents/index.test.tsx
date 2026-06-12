/**
 * R16 contract tests for the Agents page.
 *
 * Fixtures in __fixtures__/ were captured from the real backend
 * (recette.api running locally), not invented. The api client module is
 * mocked so the page renders against the exact payload shape the backend
 * returns.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentConfig, AiBackend } from "../../types/platform";
import agentsFixture from "./__fixtures__/agents.fixture.json";
import backendsFixture from "./__fixtures__/ai-backends.fixture.json";

vi.mock("../../api/client", () => ({
  listAgents: vi.fn(),
  createAgent: vi.fn(),
  updateAgent: vi.fn(),
  deleteAgent: vi.fn(),
  listAiBackends: vi.fn(),
  createAiBackend: vi.fn(),
  deleteAiBackend: vi.fn(),
  testAiBackend: vi.fn(),
  listAgentActions: vi.fn(),
  launchLaneB: vi.fn(),
  openRunSocket: vi.fn(),
  stopRun: vi.fn(),
}));

import {
  createAgent,
  launchLaneB,
  listAgentActions,
  listAgents,
  listAiBackends,
  openRunSocket,
} from "../../api/client";
import AgentsPage from "./index";

/** Minimal stand-in for the run WebSocket (useRunStream assigns handlers). */
interface FakeSocket {
  onopen: (() => void) | null;
  onmessage: ((ev: { data: string }) => void) | null;
  onerror: (() => void) | null;
  close: () => void;
}

function makeFakeSocket(): FakeSocket {
  return { onopen: null, onmessage: null, onerror: null, close: vi.fn() };
}

/** Push one frame through the fake socket as the backend would. */
function pushFrame(socket: FakeSocket, frame: Record<string, unknown>): void {
  socket.onmessage?.({ data: JSON.stringify(frame) });
}

const AGENT_ACTIONS = [
  { target_system: "github", action: "read_repo", description: "Read repo (read-only).", kind: "read" },
  { target_system: "github", action: "open_pr", description: "Open a PR (bounded write).", kind: "bounded_write" },
];

const agents = agentsFixture as unknown as AgentConfig[];
const backends = backendsFixture as unknown as AiBackend[];

describe("AgentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders agents and backends from the real fixture payloads", async () => {
    vi.mocked(listAgents).mockResolvedValue(agents);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);

    render(<AgentsPage />);

    // Agent row fields from the captured fixture (Lane B test agent).
    expect(await screen.findByText("gh-pr-bot")).toBeInTheDocument();
    expect(screen.getByText("open a pull request on acme/x")).toBeInTheDocument();
    // "github" appears in both the target and the capability-scope columns.
    expect(screen.getAllByText("github").length).toBeGreaterThanOrEqual(1);

    // The agent's AI backend select offers backend-1 plus the empty option.
    const backendSelect = screen.getByLabelText(/AI backend \(/);
    const options = within(backendSelect).getAllByRole("option");
    expect(options.map((o) => (o as HTMLOptionElement).value)).toContain(
      "backend-1",
    );
    expect(options.map((o) => (o as HTMLOptionElement).value)).toContain("");

    // No error banner on the happy path.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error banner when the agents API call fails", async () => {
    vi.mocked(listAgents).mockRejectedValue(
      new Error("API request failed (500) on /config/agents: boom"),
    );
    vi.mocked(listAiBackends).mockResolvedValue(backends);

    render(<AgentsPage />);

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(
      "API request failed (500) on /config/agents: boom",
    );
  });

  it("composes capability_scope + mock scenario from the chosen catalog actions", async () => {
    vi.mocked(listAgents).mockResolvedValue([]);
    vi.mocked(listAiBackends).mockResolvedValue([]);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(createAgent).mockResolvedValue({} as never);

    render(<AgentsPage />);

    // Wait for the catalog to load (the github option appears), then scope to it.
    await screen.findByRole("option", { name: "github" });
    fireEvent.change(screen.getByLabelText("Target system (en face)"), {
      target: { value: "github" },
    });

    // Then pick read_repo + open_pr from that system's catalog.
    fireEvent.click(await screen.findByRole("checkbox", { name: /read_repo/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /open_pr/ }));

    // "Id" labels both the agent form and the AI-backend form; the agent one is first.
    fireEvent.change(screen.getAllByLabelText("Id")[0], {
      target: { value: "pr-bot" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(createAgent).toHaveBeenCalledTimes(1);
    const payload = vi.mocked(createAgent).mock.calls[0][0];
    expect(payload.id).toBe("pr-bot");
    expect(payload.ai_mode).toBe("mock");
    expect(payload.capability_scope).toEqual(["read_repo", "open_pr"]);
    // Scenario = one tool_call per action, then a final step.
    expect(payload.scenario).toEqual([
      { kind: "tool_call", tool_name: "read_repo", tool_args: { resource: "acme/x" } },
      { kind: "tool_call", tool_name: "open_pr", tool_args: { resource: "acme/x" } },
      { kind: "final", text: "done" },
    ]);
  });

  it("runs an agent and streams its frames into the Run log console", async () => {
    vi.mocked(listAgents).mockResolvedValue(agents);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "r1", status: "pending" });
    const socket = makeFakeSocket();
    vi.mocked(openRunSocket).mockReturnValue(socket as unknown as WebSocket);

    render(<AgentsPage />);

    // The run LogConsole is mounted (empty state) before any run is launched
    // (the AI-backends panel mounts its own "Provider calls" console).
    expect(screen.getByText("Run log")).toBeInTheDocument();
    expect(screen.getAllByText("no log lines").length).toBeGreaterThanOrEqual(1);

    // Launch the fixture agent: it is bound to backend-1 (real AI), so the
    // launch body carries no stub_script.
    const row = (await screen.findByText("gh-pr-bot")).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Run" }));
    await waitFor(() =>
      expect(launchLaneB).toHaveBeenCalledWith({ agent_id: "gh-pr-bot" }),
    );

    // Frame shapes mirror the live lane_b stream (start/step/error/end).
    act(() => {
      socket.onopen?.();
      pushFrame(socket, { seq: 1, type: "start", data: { kind: "lane_b" } });
      pushFrame(socket, {
        seq: 2,
        type: "step",
        data: { index: 0, action: { action_type: "open_pr", target_system: "github" } },
      });
      pushFrame(socket, { seq: 3, type: "error", data: { message: "boom" } });
      pushFrame(socket, { seq: 4, type: "end", data: { status: "error" } });
    });

    expect(screen.getByText("step #0: open_pr@github")).toBeInTheDocument();
    const errorRow = screen.getByText("error: boom").closest(".logc-line");
    expect(errorRow).toHaveAttribute("data-level", "error");
    const infoRow = screen.getByText("step #0: open_pr@github").closest(".logc-line");
    expect(infoRow).toHaveAttribute("data-level", "info");
    // The source column of each line is the launched agent's id.
    expect(within(errorRow as HTMLElement).getByText("gh-pr-bot")).toBeInTheDocument();
  });

  it("runs a mock agent with its stored scenario as the stub script", async () => {
    const scenario = [
      { kind: "tool_call", tool_name: "read_repo", tool_args: { resource: "acme/x" } },
      { kind: "final", text: "done" },
    ];
    // Derived from the captured fixture agent: same shape, mock brain with the
    // stored scenario the page itself composes (scenarioFromActions).
    const mockAgent: AgentConfig = {
      ...agents[0],
      id: "gh-reader",
      ai_mode: "mock",
      ai_backend_id: undefined,
      scenario,
    };
    vi.mocked(listAgents).mockResolvedValue([mockAgent]);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "r2", status: "pending" });
    vi.mocked(openRunSocket).mockReturnValue(makeFakeSocket() as unknown as WebSocket);

    render(<AgentsPage />);

    const row = (await screen.findByText("gh-reader")).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Run" }));

    await waitFor(() =>
      expect(launchLaneB).toHaveBeenCalledWith({
        agent_id: "gh-reader",
        stub_script: scenario,
      }),
    );
  });
});
