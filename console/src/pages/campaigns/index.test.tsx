/**
 * Tests for the Campaigns page run console.
 *
 * The api client module is mocked; streamed frame shapes mirror the campaign
 * runner emits (recette/api/runners.py: agent_start / step / step_error /
 * campaign_done / end). The run console is the reusable LogConsole: step and
 * run failures must render as error-level lines.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Campaign } from "../../types/platform";

vi.mock("../../api/client", () => ({
  createCampaign: vi.fn(),
  deleteCampaign: vi.fn(),
  instantiateTemplate: vi.fn(),
  listAgents: vi.fn(),
  listCampaigns: vi.fn(),
  listCampaignTemplates: vi.fn(),
  listRecordings: vi.fn(),
  listRuns: vi.fn(),
  replayRecording: vi.fn(),
  runCampaign: vi.fn(),
  openRunSocket: vi.fn(),
  stopRun: vi.fn(),
}));

import {
  listAgents,
  listCampaigns,
  listCampaignTemplates,
  listRecordings,
  listRuns,
  openRunSocket,
  replayRecording,
  runCampaign,
} from "../../api/client";
import CampaignsPage from "./index";

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

const campaign: Campaign = {
  id: "camp-1",
  description: "one mock agent",
  steps: [{ agent_id: "gh-reader" }],
};

function mockEmptyLists(): void {
  vi.mocked(listCampaigns).mockResolvedValue([]);
  vi.mocked(listAgents).mockResolvedValue([]);
  vi.mocked(listRecordings).mockResolvedValue([]);
  vi.mocked(listCampaignTemplates).mockResolvedValue([]);
  vi.mocked(listRuns).mockResolvedValue([]);
}

describe("CampaignsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the LogConsole run console with its empty state", async () => {
    mockEmptyLists();

    render(<CampaignsPage />);

    // The run console stays mounted below the tabs (visible from any tab).
    expect(screen.getByText("Console du run")).toBeInTheDocument();
    expect(screen.getByText("no log lines")).toBeInTheDocument();
    // Campaigns list lives behind the "Campagnes" tab.
    fireEvent.click(screen.getByRole("tab", { name: "Campagnes" }));
    await screen.findByText(
      "Aucune campagne. Cree-en une depuis l'onglet Modeles ou Creer.",
    );
  });

  it("streams campaign frames into the console; step_error is error-level", async () => {
    mockEmptyLists();
    vi.mocked(listCampaigns).mockResolvedValue([campaign]);
    vi.mocked(runCampaign).mockResolvedValue({ run_id: "r1", status: "pending" });
    const socket = makeFakeSocket();
    vi.mocked(openRunSocket).mockReturnValue(socket as unknown as WebSocket);

    render(<CampaignsPage />);

    // The campaign list and its Lancer button live behind the "Campagnes" tab.
    fireEvent.click(screen.getByRole("tab", { name: "Campagnes" }));
    fireEvent.click(await screen.findByRole("button", { name: "Lancer" }));
    await waitFor(() => expect(runCampaign).toHaveBeenCalledWith("camp-1"));

    act(() => {
      socket.onopen?.();
      pushFrame(socket, {
        seq: 1,
        type: "agent_start",
        data: { agent_id: "gh-reader", provider: "stub" },
      });
      pushFrame(socket, {
        seq: 2,
        type: "step_error",
        data: { index: 0, agent_id: "gh-reader", message: "mock agent has no scenario" },
      });
      pushFrame(socket, { seq: 3, type: "end", data: { status: "done" } });
    });

    // Frame summaries keep the previous semantics (frameLine).
    expect(screen.getByText("agent_start gh-reader (stub)")).toBeInTheDocument();
    const errorRow = screen
      .getByText("step_error gh-reader: mock agent has no scenario")
      .closest(".logc-line");
    expect(errorRow).toHaveAttribute("data-level", "error");
    const infoRow = screen
      .getByText("agent_start gh-reader (stub)")
      .closest(".logc-line");
    expect(infoRow).toHaveAttribute("data-level", "info");
    // Each line is sourced to the acting agent.
    expect(screen.getAllByText("gh-reader").length).toBeGreaterThanOrEqual(2);
  });

  it("replays a recording at the selected slow-motion pace", async () => {
    mockEmptyLists();
    vi.mocked(listRecordings).mockResolvedValue([
      { recording_id: "rec-1", agent_id: "gh-reader", steps: 3 } as never,
    ]);
    vi.mocked(replayRecording).mockResolvedValue({ run_id: "r2", status: "pending" });
    vi.mocked(openRunSocket).mockReturnValue(makeFakeSocket() as unknown as WebSocket);

    render(<CampaignsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Enregistrements" }));

    // Default pace is instant (0); pick the 1.5s/step slow-motion speed.
    const pace = await screen.findByTestId("replay-pace");
    fireEvent.change(pace, { target: { value: "1500" } });
    fireEvent.click(await screen.findByRole("button", { name: "Replay" }));
    await waitFor(() => expect(replayRecording).toHaveBeenCalledWith("rec-1", 1500));
  });

  it("disables the campaign eye until the campaign has a run", async () => {
    mockEmptyLists();
    vi.mocked(listCampaigns).mockResolvedValue([campaign]);
    // No run for camp-1 -> eye is present but disabled (nothing to view).
    vi.mocked(listRuns).mockResolvedValue([]);

    render(<CampaignsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Campagnes" }));

    const eye = await screen.findByRole("button", { name: "Voir le run de camp-1" });
    expect(eye).toBeDisabled();
  });

  it("enables the campaign eye once a run exists for the campaign", async () => {
    mockEmptyLists();
    vi.mocked(listCampaigns).mockResolvedValue([campaign]);
    vi.mocked(listRuns).mockResolvedValue([
      {
        id: "r1",
        kind: "campaign",
        status: "completed",
        agent_id: null,
        campaign_id: "camp-1",
        error: null,
      },
    ]);

    render(<CampaignsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Campagnes" }));

    const eye = await screen.findByRole("button", { name: "Voir le run de camp-1" });
    await waitFor(() => expect(eye).toBeEnabled());
  });
});
