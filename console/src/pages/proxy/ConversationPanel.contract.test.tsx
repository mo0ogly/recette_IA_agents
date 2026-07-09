/**
 * R16 contract test for ConversationPanel -- the unified agent conversation.
 *
 * The api client is mocked with the exact payload shapes the backend returns
 * (RunSummary[], LlmTracesResult, ProxyTraceResponse). The panel must join the
 * LLM decision (thought) and the agent<->server exchange (request + server
 * response) for the selected run into one ordered conversation.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listRuns: vi.fn(),
    getLlmTraces: vi.fn(),
    getProxyTraces: vi.fn(),
  };
});

import { getLlmTraces, getProxyTraces, listRuns } from "../../api/client";
import ConversationPanel from "./ConversationPanel";

const RUNS = [
  {
    id: "run-1",
    kind: "lane_b",
    status: "completed",
    agent_id: "maintainer",
    campaign_id: null,
    error: null,
  },
];

const LLM = {
  run_id: "run-1",
  count: 2,
  traces: [
    {
      seq: 1,
      event_id: "e1",
      agent_id: "a1",
      model: "gpt-4o",
      kind: "tool_call",
      tool_name: "read_repo",
      resource: "acme/x",
      intent: "read acme/x",
      prompt_tokens: 10,
      completion_tokens: 5,
      total_tokens: 15,
      latency_ms: 0,
      error: null,
    },
    {
      seq: 2,
      event_id: "e2",
      agent_id: "a1",
      model: "gpt-4o",
      kind: "final",
      tool_name: null,
      resource: "",
      intent: "done",
      prompt_tokens: 3,
      completion_tokens: 2,
      total_tokens: 5,
      latency_ms: 0,
      error: null,
    },
  ],
};

const PROXY = {
  debug_enabled: true,
  last_seq: 1,
  total: 1,
  reset: false,
  traces: [
    {
      seq: 1,
      event_id: "e1",
      timestamp: "t",
      agent_id: "a1",
      target_system: "github",
      action_type: "read_repo",
      resource: "acme/x",
      request_payload: { q: "x" },
      ok: true,
      status_code: 200,
      side_effect_hash: null,
      error: null,
      run_id: "run-1",
      response: { number: 42 },
    },
  ],
};

function renderPanel(entries: string[] = ["/proxy?source=conversation&run=run-1"]): void {
  render(
    <MemoryRouter initialEntries={entries}>
      <ConversationPanel />
    </MemoryRouter>,
  );
}

describe("ConversationPanel (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listRuns).mockResolvedValue(RUNS as never);
    vi.mocked(getLlmTraces).mockResolvedValue(LLM as never);
    vi.mocked(getProxyTraces).mockResolvedValue(PROXY as never);
  });

  it("joins the LLM thought and the server exchange for a run", async () => {
    renderPanel();
    await screen.findByTestId("conversation-list");
    // Turn 1: the thought (model + decided tool) AND the server response.
    const think = screen.getByTestId("conv-think-1");
    expect(think).toHaveTextContent("gpt-4o");
    expect(think).toHaveTextContent("read_repo");
    const exchange = screen.getByTestId("conv-exchange-1");
    expect(exchange).toHaveTextContent("reponse serveur");
    expect(exchange).toHaveTextContent("42");
    // Turn 2: a final decision, no server exchange.
    expect(screen.getByTestId("conv-think-2")).toHaveTextContent("final");
    expect(screen.queryByTestId("conv-exchange-2")).toBeNull();
  });

  it("fetches BOTH halves (llm decisions + server traces) for the selected run", async () => {
    renderPanel();
    await screen.findByTestId("conversation-list");
    await waitFor(() => expect(getLlmTraces).toHaveBeenCalledWith("run-1"));
    await waitFor(() => expect(getProxyTraces).toHaveBeenCalledWith(undefined, "run-1"));
  });

  it("shows a hint (not an empty list) when no run is selected", async () => {
    renderPanel(["/proxy?source=conversation"]);
    expect(await screen.findByTestId("conversation-hint")).toBeInTheDocument();
    expect(screen.queryByTestId("conversation-list")).toBeNull();
  });

  it("lists runs across agents and campaigns in the picker", async () => {
    renderPanel(["/proxy?source=conversation"]);
    const select = await screen.findByTestId("conversation-run");
    await waitFor(() => expect(select).toHaveTextContent("maintainer"));
  });
});
