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

    expect(screen.getByText("Console du run")).toBeInTheDocument();
    expect(screen.getByText("no log lines")).toBeInTheDocument();
    await screen.findByText("Aucune campagne. Cree-en une a droite.");
  });

  it("streams campaign frames into the console; step_error is error-level", async () => {
    mockEmptyLists();
    vi.mocked(listCampaigns).mockResolvedValue([campaign]);
    vi.mocked(runCampaign).mockResolvedValue({ run_id: "r1", status: "pending" });
    const socket = makeFakeSocket();
    vi.mocked(openRunSocket).mockReturnValue(socket as unknown as WebSocket);

    render(<CampaignsPage />);

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
});
