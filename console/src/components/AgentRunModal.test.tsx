/**
 * AgentRunModal tests (R16 contract gate) -- render-and-assert against a real
 * captured /runs/{id}/events payload (__fixtures__/agentRun.fixture.json) plus
 * an injected RunSummary list for the run-history (Journal) tab.
 *
 * The lazy MonacoJsonViewer cannot run under jsdom, so it is mocked with a
 * textarea exposing the JSON value. The snapshot fetcher and socket factory are
 * injected so no real backend or WebSocket is touched.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import AgentRunModal from "./AgentRunModal";
import type {
  RunEvent,
  RunSummary,
  RunVerdict,
  RunVerdictSubmission,
} from "../types/platform";
import runFixture from "./__fixtures__/agentRun.fixture.json";

vi.mock("./MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => (
    <textarea readOnly data-testid="monaco-stub" value={value} />
  ),
}));

const frames = runFixture as unknown as RunEvent[];

const RUNS: RunSummary[] = [
  { id: "run-aaaaaaaaaaaa1", kind: "lane_b", status: "completed", agent_id: "camp-identity-admin", campaign_id: null, error: null },
  { id: "run-bbbbbbbbbbbb2", kind: "lane_b", status: "failed", agent_id: "camp-identity-admin", campaign_id: null, error: "boom" },
  { id: "run-cccccccccccc3", kind: "lane_b", status: "completed", agent_id: "other-agent", campaign_id: null, error: null },
];

function fakeSocket(): WebSocket {
  return {
    onopen: null,
    onclose: null,
    onerror: null,
    onmessage: null,
    close: () => undefined,
  } as unknown as WebSocket;
}

const VERDICT: RunVerdict = {
  run_id: "run-aaaaaaaaaaaa1",
  agent_id: "camp-identity-admin",
  action_count: 1,
  verdict: "incorrect",
  dimensions: { identity: true, capabilities: false, policy: true, behavior: true },
  capability_violations: [
    {
      observed_action: "delete_user",
      kind: "undeclared_action",
      note: "action 'delete_user' not in declared capability_scope",
    },
  ],
};

const TRACES_RESPONSE = {
  debug_enabled: true,
  traces: [
    {
      seq: 1,
      event_id: "evt-0001",
      timestamp: "2026-06-14T00:00:00Z",
      agent_id: "camp-identity-admin",
      target_system: "okta",
      action_type: "suspend_user",
      resource: "acme/jdoe",
      request_payload: {},
      ok: true,
      status_code: 200,
      side_effect_hash: "abc",
      error: null,
      run_id: "run-aaaaaaaaaaaa1",
      response: { action: "suspend_user", status: "SUSPENDED", user_id: "00u-jdoe" },
    },
  ],
  last_seq: 1,
  total: 1,
  reset: false,
};

const SUBMISSION: RunVerdictSubmission = {
  run_id: "run-aaaaaaaaaaaa1",
  agent_id: "camp-identity-admin",
  submitted_seq: 7,
  judged: [{ agent_id: "camp-identity-admin", status: "FAIL", checks: { verdict: false } }],
};

interface Overrides {
  open?: boolean;
  runId?: string | null;
  onPurge?: (id: string) => Promise<void> | void;
  fetchVerdict?: (runId: string) => Promise<RunVerdict>;
  fetchTraces?: (runId: string) => Promise<typeof TRACES_RESPONSE>;
  submitVerdict?: (runId: string) => Promise<RunVerdictSubmission>;
  frames?: RunEvent[];
}

function renderModal(o: Overrides = {}): void {
  render(
    <MemoryRouter>
      <AgentRunModal
        open={o.open ?? true}
        agentId="camp-identity-admin"
        runId={o.runId === undefined ? "run-aaaaaaaaaaaa1" : o.runId}
        status="completed"
        runs={RUNS}
        onClose={vi.fn()}
        onPurge={o.onPurge}
        fetchEvents={() => Promise.resolve(o.frames ?? frames)}
        socketFactory={fakeSocket}
        fetchVerdict={o.fetchVerdict ?? (() => Promise.resolve(VERDICT))}
        fetchTraces={o.fetchTraces ?? (() => Promise.resolve(TRACES_RESPONSE))}
        submitVerdict={o.submitVerdict ?? (() => Promise.resolve(SUBMISSION))}
      />
    </MemoryRouter>,
  );
}

describe("AgentRunModal", () => {
  it("renders nothing when closed", () => {
    renderModal({ open: false });
    expect(screen.queryByTestId("monaco-stub")).toBeNull();
  });

  it("shows the current run frames in the JSON tab", async () => {
    renderModal();
    const editor = await screen.findByTestId("monaco-stub");
    await waitFor(() => {
      const view = JSON.parse((editor as HTMLTextAreaElement).value) as {
        agent_id: string;
        frame_count: number;
      };
      expect(view.agent_id).toBe("camp-identity-admin");
      expect(view.frame_count).toBe(frames.length);
    });
  });

  it("lists only this agent's runs in the history tab", async () => {
    renderModal();
    fireEvent.click(screen.getByRole("tab", { name: /Historique/ }));
    const journal = screen.getByTestId("run-journal");
    const rows = within(journal).getAllByTestId("run-journal-row");
    // Two runs belong to camp-identity-admin; the third (other-agent) is filtered out.
    expect(rows.length).toBe(2);
    expect(journal.textContent).toMatch(/erreur/); // failed run -> voyant erreur
    expect(screen.queryByTestId("monaco-stub")).toBeNull();
    // Each run's frames are fetched and rendered as a detailed log line
    // (frameToLine): the fixture's write action becomes an action line.
    await waitFor(() => {
      const lines = within(journal).getAllByText(/suspend_user -> okta acme\/jdoe \[write\]/);
      // One detailed line per camp-identity-admin run (both share the fixture).
      expect(lines.length).toBe(2);
    });
  });

  it("shows the 4-dimension recette verdict with typed violations (F1)", async () => {
    renderModal();
    fireEvent.click(screen.getByRole("tab", { name: /Verdict/ }));
    const panel = await screen.findByTestId("run-verdict");
    // Global verdict + the broken dimension's typed violation are surfaced.
    expect(panel.textContent).toMatch(/incorrect/);
    expect(within(panel).getByText("undeclared_action")).toBeInTheDocument();
    expect(within(panel).getByText("delete_user")).toBeInTheDocument();
    // One "violation" label (capabilities) among the conforming dimensions.
    expect(within(panel).getAllByText("violation").length).toBe(1);
    expect(within(panel).getAllByText("conforme").length).toBe(3);
  });

  it("submits the run to the Verdicts board and links to it", async () => {
    const submitVerdict = vi.fn().mockResolvedValue(SUBMISSION);
    renderModal({ submitVerdict });
    fireEvent.click(screen.getByRole("tab", { name: /Verdict/ }));
    await screen.findByTestId("run-verdict");
    fireEvent.click(screen.getByTestId("submit-verdict-btn"));
    await waitFor(() =>
      expect(submitVerdict).toHaveBeenCalledWith("run-aaaaaaaaaaaa1"),
    );
    const ok = await screen.findByTestId("submit-verdict-ok");
    // The judged status of the submission and a link to the board are shown.
    expect(ok.textContent).toMatch(/FAIL/);
    expect(within(ok).getByRole("link", { name: /Verdicts/ })).toHaveAttribute(
      "href",
      "/verdicts",
    );
  });

  it("surfaces a submit-to-board error", async () => {
    renderModal({ submitVerdict: () => Promise.reject(new Error("board down")) });
    fireEvent.click(screen.getByRole("tab", { name: /Verdict/ }));
    await screen.findByTestId("run-verdict");
    fireEvent.click(screen.getByTestId("submit-verdict-btn"));
    const alert = await screen.findByText("board down");
    expect(alert).toBeInTheDocument();
  });

  it("surfaces a verdict fetch error", async () => {
    renderModal({ fetchVerdict: () => Promise.reject(new Error("judge down")) });
    fireEvent.click(screen.getByRole("tab", { name: /Verdict/ }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("judge down");
  });

  it("pairs each LLM decision with its side effect in the Decide tab (F2)", async () => {
    const decideFrames = [
      {
        seq: 1,
        type: "step",
        data: {
          index: 0,
          decision: { kind: "tool_call", tool_name: "suspend_user", tool_args: { resource: "acme/jdoe" }, text: "" },
          action: { action_type: "suspend_user", target_system: "okta", resource: "acme/jdoe", mode: "write" },
        },
      },
    ] as unknown as RunEvent[];
    renderModal({ frames: decideFrames });
    fireEvent.click(screen.getByRole("tab", { name: /Decide/ }));
    const decide = await screen.findByTestId("run-decide");
    // The decision (what the LLM chose) and the action (what executed) are paired.
    expect(decide.textContent).toMatch(/suspend_user\(acme\/jdoe\)/);
    expect(decide.textContent).toMatch(/suspend_user -> okta\/acme\/jdoe/);
  });

  it("deep-links the run's proxy traces in the Traces tab", async () => {
    renderModal();
    fireEvent.click(screen.getByRole("tab", { name: /Traces proxy/ }));
    const list = await screen.findByTestId("run-traces");
    expect(list.textContent).toMatch(/suspend_user -> okta\/acme\/jdoe/);
  });

  it("shows the debug-off hint when proxy tracing is disabled", async () => {
    renderModal({
      fetchTraces: () => Promise.resolve({ debug_enabled: false, traces: [], last_seq: 0, total: 0, reset: false }),
    });
    fireEvent.click(screen.getByRole("tab", { name: /Traces proxy/ }));
    const empty = await screen.findByTestId("run-traces-empty");
    expect(empty.textContent).toMatch(/INSPECT_IA_AGENTS_PROXY_DEBUG/);
  });

  it("purges this agent's runs via onPurge", async () => {
    const onPurge = vi.fn().mockResolvedValue(undefined);
    renderModal({ onPurge });
    fireEvent.click(screen.getByRole("tab", { name: /Historique/ }));
    fireEvent.click(screen.getByRole("button", { name: /Purger/ }));
    await waitFor(() => expect(onPurge).toHaveBeenCalledWith("camp-identity-admin"));
  });
});

// Campaign mode: the same modal becomes the eye of a multi-agent campaign run.
const CAMPAIGN_FRAMES: RunEvent[] = [
  { seq: 1, type: "agent_start", data: { index: 0, agent_id: "gh-pr-bot", provider: "stub" } },
  {
    seq: 2,
    type: "step",
    data: {
      index: 0,
      agent_id: "gh-pr-bot",
      action: { action_type: "open_pr", target_system: "github", resource: "acme/repo" },
    },
  },
  {
    seq: 3,
    type: "agent_done",
    data: { index: 0, agent_id: "gh-pr-bot", actions: 1, recording_id: "camp-1.00.gh-pr-bot" },
  },
  { seq: 4, type: "agent_start", data: { index: 1, agent_id: "camp-rogue-bot", provider: "stub" } },
  {
    seq: 5,
    type: "step_error",
    data: { index: 1, agent_id: "camp-rogue-bot", message: "capability overreach" },
  },
  { seq: 6, type: "campaign_done", data: { campaign_id: "camp-1", steps: 2 } },
  { seq: 7, type: "end", data: { status: "done" } },
] as unknown as RunEvent[];

const CAMPAIGN_RUNS: RunSummary[] = [
  { id: "crun-111111111", kind: "campaign", status: "completed", agent_id: null, campaign_id: "camp-1", error: null },
  { id: "run-zzzzzzzzzz9", kind: "lane_b", status: "completed", agent_id: "gh-pr-bot", campaign_id: null, error: null },
];

function renderCampaign(frames?: RunEvent[]): void {
  render(
    <MemoryRouter>
      <AgentRunModal
        open
        agentId=""
        campaignId="camp-1"
        steps={[{ agent_id: "gh-pr-bot" }, { agent_id: "camp-rogue-bot" }]}
        runId="crun-111111111"
        status="completed"
        runs={CAMPAIGN_RUNS}
        onClose={vi.fn()}
        fetchEvents={() => Promise.resolve(frames ?? CAMPAIGN_FRAMES)}
        socketFactory={fakeSocket}
        fetchVerdict={() => Promise.resolve(VERDICT)}
        fetchTraces={() => Promise.resolve(TRACES_RESPONSE)}
        submitVerdict={() => Promise.resolve(SUBMISSION)}
      />
    </MemoryRouter>,
  );
}

describe("AgentRunModal campaign mode", () => {
  it("titles the modal as a campaign and defaults to the Etapes tab", async () => {
    renderCampaign();
    expect(screen.getByRole("heading", { name: /Campagne camp-1/ })).toBeInTheDocument();
    // The Etapes tab is campaign-only and selected by default.
    expect(screen.getByRole("tab", { name: "Etapes (agents)" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("breaks the run down per agent step (multi-agent), with actions and outcomes", async () => {
    renderCampaign();
    // Both step agents are listed, in order.
    expect(await screen.findByText("gh-pr-bot")).toBeInTheDocument();
    expect(screen.getByText("camp-rogue-bot")).toBeInTheDocument();
    // Step 1 executed an action; step 2 errored (capability overreach).
    expect(screen.getByText("open_pr -> github/acme/repo")).toBeInTheDocument();
    expect(screen.getByText("capability overreach")).toBeInTheDocument();
    expect(screen.getByText(/camp-1\.00\.gh-pr-bot/)).toBeInTheDocument();
  });

  it("filters the run history to the campaign's runs (by campaign_id)", async () => {
    renderCampaign();
    // Only the one campaign run counts, not the lane_b run in the same list.
    expect(
      screen.getByRole("tab", { name: "Historique des runs (1)" }),
    ).toBeInTheDocument();
  });

  it("shows the declared step plan before any run exists", async () => {
    render(
      <MemoryRouter>
        <AgentRunModal
          open
          agentId=""
          campaignId="camp-1"
          steps={[{ agent_id: "gh-pr-bot" }, { agent_id: "camp-rogue-bot" }]}
          runId={null}
          status=""
          runs={[]}
          onClose={vi.fn()}
          fetchEvents={() => Promise.resolve([])}
          socketFactory={fakeSocket}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/etapes declarees/i)).toBeInTheDocument();
    expect(screen.getByText("gh-pr-bot")).toBeInTheDocument();
    expect(screen.getAllByText("pas lance").length).toBe(2);
  });
});
