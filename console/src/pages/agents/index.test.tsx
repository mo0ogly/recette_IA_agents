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
import agentsWithPaceFixture from "./__fixtures__/agents-with-pace.fixture.json";
import backendsFixture from "./__fixtures__/ai-backends.fixture.json";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listAgents: vi.fn(),
    createAgent: vi.fn(),
    updateAgent: vi.fn(),
    deleteAgent: vi.fn(),
    listAiBackends: vi.fn(),
    createAiBackend: vi.fn(),
    deleteAiBackend: vi.fn(),
    testAiBackend: vi.fn(),
    listAgentActions: vi.fn(),
    listSubjects: vi.fn(() => Promise.resolve({ count: 0, families: {}, subjects: [] })),
    launchLaneB: vi.fn(),
    openRunSocket: vi.fn(),
    stopRun: vi.fn(),
    listRuns: vi.fn(() => Promise.resolve([])),
    getRunEvents: vi.fn(() => Promise.resolve([])),
    getRunVerdict: vi.fn(() => Promise.resolve({})),
    getProxyTraces: vi.fn(() => Promise.resolve({ debug_enabled: false, traces: [] })),
    purgeRuns: vi.fn(() => Promise.resolve({ removed: 0 })),
  };
});

import {
  createAgent,
  launchLaneB,
  listAgentActions,
  listAgents,
  listAiBackends,
  openRunSocket,
  updateAgent,
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

/** Navigate the creation/edit wizard to the step whose label matches. */
function gotoStep(label: string): void {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`\\d\\. ${label}`) }));
}

const agents = agentsFixture as unknown as AgentConfig[];
const agentsWithPace = agentsWithPaceFixture as unknown as AgentConfig[];
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

    // The agent's AI backend select offers backend-1 plus the empty option
    // (it lives on the wizard's IA step).
    gotoStep("IA");
    const backendSelect = screen.getByLabelText(/AI backend \(/);
    const options = within(backendSelect).getAllByRole("option");
    expect(options.map((o) => (o as HTMLOptionElement).value)).toContain(
      "backend-1",
    );
    expect(options.map((o) => (o as HTMLOptionElement).value)).toContain("");

    // No error banner on the happy path.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("opens the precise launch modal for an agent row", async () => {
    vi.mocked(listAgents).mockResolvedValue(agents);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);

    render(<AgentsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /lancer precis pour gh-pr-bot/i }));
    await waitFor(() =>
      expect(
        screen.getByRole("dialog", { name: /lancer une instance precise/i }),
      ).toBeInTheDocument(),
    );
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

    // Cible step: scope to the github system (catalog loaded).
    gotoStep("Cible");
    await screen.findByRole("option", { name: "github" });
    fireEvent.change(screen.getByLabelText("Target system (en face)"), {
      target: { value: "github" },
    });

    // Tools step: pick read_repo + open_pr from that system's catalog.
    gotoStep("Tools");
    fireEvent.click(await screen.findByRole("checkbox", { name: /read_repo/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /open_pr/ }));

    // Identite step: set the agent id, then review + create.
    gotoStep("Identite");
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "pr-bot" } });
    gotoStep("Revue");
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

  it("composes a bounded-memory block from the memory fields", async () => {
    vi.mocked(listAgents).mockResolvedValue([]);
    vi.mocked(listAiBackends).mockResolvedValue([]);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(createAgent).mockResolvedValue({} as never);

    render(<AgentsPage />);

    await screen.findByText("Agents");
    gotoStep("Identite");
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "mem-bot" } });

    // Memoire step: enable bounded memory and set the sliding-window size.
    gotoStep("Memoire");
    fireEvent.click(screen.getByRole("checkbox", { name: /Borner le contexte/ }));
    fireEvent.change(screen.getByLabelText("Fenetre (messages)"), {
      target: { value: "5" },
    });
    gotoStep("Revue");
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(createAgent).toHaveBeenCalledTimes(1);
    const payload = vi.mocked(createAgent).mock.calls[0][0];
    expect(payload.memory).toEqual({ enabled: true, window: 5 });
  });

  it("omits memory when the bounded-memory toggle is off", async () => {
    vi.mocked(listAgents).mockResolvedValue([]);
    vi.mocked(listAiBackends).mockResolvedValue([]);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(createAgent).mockResolvedValue({} as never);

    render(<AgentsPage />);
    await screen.findByText("Agents");
    gotoStep("Identite");
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "no-mem" } });
    gotoStep("Revue");
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    const payload = vi.mocked(createAgent).mock.calls[0][0];
    expect(payload.memory).toBeUndefined();
  });

  it("Revue step previews the composed config and blocks Create on invalid scenario JSON", async () => {
    vi.mocked(listAgents).mockResolvedValue([]);
    vi.mocked(listAiBackends).mockResolvedValue([]);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(createAgent).mockResolvedValue({} as never);

    render(<AgentsPage />);
    await screen.findByText("Agents");

    gotoStep("Identite");
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "rev-bot" } });

    // A malformed advanced scenario makes the preview an error and disables Create.
    gotoStep("Tools");
    fireEvent.change(screen.getByLabelText("Scenario (JSON, avance)"), {
      target: { value: "{ not json" },
    });
    gotoStep("Revue");
    expect(screen.getByRole("alert")).toHaveTextContent("Scenario JSON invalide");
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();

    // Clearing it restores a valid preview (id is shown) and re-enables Create.
    gotoStep("Tools");
    fireEvent.change(screen.getByLabelText("Scenario (JSON, avance)"), {
      target: { value: "" },
    });
    gotoStep("Revue");
    expect(screen.getByTestId("agents-preview")).toHaveTextContent("rev-bot");
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(createAgent).toHaveBeenCalledTimes(1);
  });

  it("edit form exposes role/model/system_prompt/ground_truth and preserves them on save", async () => {
    const rich: AgentConfig = {
      ...agents[0],
      id: "rich-bot",
      role: "finance_admin",
      model: "llama-3.3-70b-versatile",
      system_prompt: "You are the finance agent.",
      ai_mode: "real",
      ground_truth: {
        detectable: true,
        expected_verdict: "correct",
        expected_identity: "bot@acme",
        dimensions: { identity: true, capabilities: true, policy: true, behavior: true },
      },
    };
    vi.mocked(listAgents).mockResolvedValue([rich]);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(updateAgent).mockResolvedValue({} as never);

    render(<AgentsPage />);

    const row = (await screen.findByText("rich-bot")).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));

    // IA step: the rich AI properties are populated from the edited agent.
    gotoStep("IA");
    expect((screen.getByLabelText("Role") as HTMLInputElement).value).toBe("finance_admin");
    expect((screen.getByLabelText("Model") as HTMLInputElement).value).toBe(
      "llama-3.3-70b-versatile",
    );
    const prompt = screen.getByLabelText("System prompt") as HTMLTextAreaElement;
    expect(prompt.value).toBe("You are the finance agent.");

    // Ground-truth step: the inline expected verdict is populated too.
    gotoStep("Ground-truth");
    expect((screen.getByLabelText("Identite attendue") as HTMLInputElement).value).toBe(
      "bot@acme",
    );
    expect((screen.getByRole("checkbox", { name: "detectable" }) as HTMLInputElement).checked).toBe(
      true,
    );

    // Change the system prompt (back on the IA step) and save: the payload
    // carries the new prompt AND the preserved role/model/ground_truth.
    gotoStep("IA");
    fireEvent.change(screen.getByLabelText("System prompt"), {
      target: { value: "Updated prompt." },
    });
    gotoStep("Revue");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(updateAgent).toHaveBeenCalledTimes(1));
    const [, payload] = vi.mocked(updateAgent).mock.calls[0];
    expect(payload.system_prompt).toBe("Updated prompt.");
    expect(payload.role).toBe("finance_admin");
    expect(payload.model).toBe("llama-3.3-70b-versatile");
    expect(payload.ground_truth?.expected_verdict).toBe("correct");
    expect(payload.ground_truth?.dimensions?.identity).toBe(true);
  });

  it("loads pace_ms into the Cadence (ms) field and saves an edited value as a number", async () => {
    // The real fixture's first agent (camp-rogue-bot) carries pace_ms: 800;
    // the others inherit (no pace_ms).
    vi.mocked(listAgents).mockResolvedValue(agentsWithPace);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(updateAgent).mockResolvedValue({} as never);

    render(<AgentsPage />);

    const paced = agentsWithPace[0];
    const row = (await screen.findByText(paced.id)).closest("tr") as HTMLElement;
    // Table cell shows the configured pace for the paced agent.
    expect(within(row).getByText(/pace 800ms/)).toBeInTheDocument();

    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));

    gotoStep("Cible");
    const cadence = screen.getByLabelText("Cadence (ms)") as HTMLInputElement;
    expect(cadence.value).toBe("800");

    // Editing and saving carries the new pace as a NUMBER (not a string).
    fireEvent.change(cadence, { target: { value: "1500" } });
    gotoStep("Revue");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(updateAgent).toHaveBeenCalledTimes(1));
    const [, payload] = vi.mocked(updateAgent).mock.calls[0];
    expect(payload.pace_ms).toBe(1500);
  });

  it("omits pace_ms (inherit) when the Cadence field is cleared", async () => {
    vi.mocked(listAgents).mockResolvedValue(agentsWithPace);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(updateAgent).mockResolvedValue({} as never);

    render(<AgentsPage />);

    const paced = agentsWithPace[0];
    const row = (await screen.findByText(paced.id)).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));

    gotoStep("Cible");
    const cadence = screen.getByLabelText("Cadence (ms)") as HTMLInputElement;
    fireEvent.change(cadence, { target: { value: "" } });
    gotoStep("Revue");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(updateAgent).toHaveBeenCalledTimes(1));
    const [, payload] = vi.mocked(updateAgent).mock.calls[0];
    // Cleared = inherit from server / instant, never 0 or NaN.
    expect(payload.pace_ms).toBeUndefined();
  });

  it("exposes a Corpus tab with the answer-key note distinct from the Cockpit exam", async () => {
    vi.mocked(listAgents).mockResolvedValue(agents);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);

    render(<AgentsPage />);
    await screen.findByText("gh-pr-bot");

    // Default tab (Configuration) reminds it is the workshop, not a run.
    expect(screen.getByTestId("agents-tab-note")).toHaveTextContent("L'atelier");

    // Corpus tab is the read-only answer key (school metaphor: "le corrige").
    fireEvent.click(screen.getByRole("tab", { name: "Corpus" }));
    expect(screen.getByTestId("agents-tab-note")).toHaveTextContent("Le corrige");
    expect(await screen.findByTestId("corpus-count")).toBeInTheDocument();

    // Cockpit tab is the exam: launch an agent that acts and produces a paper.
    fireEvent.click(screen.getByRole("tab", { name: /Cockpit/ }));
    expect(screen.getByTestId("agents-tab-note")).toHaveTextContent("L'examen");

    // Run log with no run started shows the hint pointing back to the Run
    // button, not a silent empty box.
    fireEvent.click(screen.getByRole("tab", { name: "Run log" }));
    expect(screen.getByTestId("agents-run-empty")).toHaveTextContent(
      "Vide tant qu'aucun run",
    );
  });

  it("runs an agent and streams its frames into the Run log console", async () => {
    vi.mocked(listAgents).mockResolvedValue(agents);
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(listAgentActions).mockResolvedValue(AGENT_ACTIONS as never);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "r1", status: "pending" });
    const socket = makeFakeSocket();
    vi.mocked(openRunSocket).mockReturnValue(socket as unknown as WebSocket);

    render(<AgentsPage />);

    // Launch the fixture agent from the Configuration table: it is bound to
    // backend-1 (real AI), so the launch body carries no stub_script.
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

    // The Run log lives in its own tab now; open it to read the streamed frames.
    fireEvent.click(screen.getByRole("tab", { name: "Run log" }));
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
