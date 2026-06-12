/**
 * R16 contract tests for the Agents page.
 *
 * Fixtures in __fixtures__/ were captured from the real backend
 * (recette.api running locally), not invented. The api client module is
 * mocked so the page renders against the exact payload shape the backend
 * returns.
 */

import { render, screen, within } from "@testing-library/react";
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
  listAgentActions: vi.fn(),
}));

import {
  listAgentActions,
  listAgents,
  listAiBackends,
} from "../../api/client";
import AgentsPage from "./index";

const AGENT_ACTIONS = [
  { action: "read_repo", description: "Read repository metadata (read-only).", kind: "read" },
  { action: "open_pr", description: "Open a pull request (bounded write).", kind: "bounded_write" },
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
});
