/**
 * R16 contract tests for the Recette page (discovery + identification runners).
 *
 * Fixtures under __fixtures__/ are the REAL frame streams captured from the
 * running API (POST /runs kind=discovery|identification, then GET
 * /runs/{id}/events until the terminal "end" frame) -- capture note: API was
 * the dev bare-host instance, the runner path is the same code the container
 * ships. The WebSocket is a hand-rolled fake (same pattern as
 * hooks/useRunStream.test.ts); the frames fed through it are the captured
 * payloads, unmodified.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { launchRunner, openRunSocket, stopRun } from "../../api/client";
import discoveryFrames from "./__fixtures__/discovery-frames.fixture.json";
import identificationFrames from "./__fixtures__/identification-frames.fixture.json";
import RecettePage from "./index";

vi.mock("../../api/client", () => ({
  launchRunner: vi.fn(),
  openRunSocket: vi.fn(),
  stopRun: vi.fn(),
}));

vi.mock("../../components/help/PageHelp", () => ({
  default: () => null,
}));

const mockLaunchRunner = vi.mocked(launchRunner);
const mockOpenRunSocket = vi.mocked(openRunSocket);
const mockStopRun = vi.mocked(stopRun);

class FakeSocket {
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  close(): void {
    this.closed = true;
  }
}

interface Frame {
  seq: number;
  type: string;
  data: Record<string, unknown>;
}

function feed(socket: FakeSocket, frames: Frame[]): void {
  act(() => {
    socket.onopen?.();
    for (const f of frames) {
      socket.onmessage?.({ data: JSON.stringify(f) });
    }
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  mockStopRun.mockResolvedValue(undefined as never);
});

describe("RecettePage", () => {
  it("shows both empty states before any run", () => {
    render(<RecettePage />);
    expect(
      screen.getByText(/Lance la recette discovery sur le corpus de repos/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Lance la recette identification sur le corpus d'agents/),
    ).toBeInTheDocument();
  });

  it("streams the captured discovery frames into the per-surface scorecard table", async () => {
    const socket = new FakeSocket();
    mockLaunchRunner.mockResolvedValue({ run_id: "run-disc", status: "pending" });
    mockOpenRunSocket.mockReturnValue(socket as unknown as WebSocket);

    render(<RecettePage />);
    fireEvent.click(screen.getByRole("button", { name: "Lancer discovery" }));
    await waitFor(() => expect(mockLaunchRunner).toHaveBeenCalledWith("discovery"));

    feed(socket, discoveryFrames as Frame[]);

    // Real capture: one scorecard row per surface (github 10/10, gitlab 5/5...).
    expect(screen.getByText("github")).toBeInTheDocument();
    expect(screen.getByText("gitlab")).toBeInTheDocument();
    const passPills = screen.getAllByText("PASS");
    expect(passPills.length).toBeGreaterThan(0);
    expect(passPills[0]).toHaveClass("pill", "pill-ok");
    // Terminal frame flips the status out of running.
    expect(screen.getByText(/run-disc/)).toBeInTheDocument();
  });

  it("streams the captured identification frames into agent rows and the summary", async () => {
    const socket = new FakeSocket();
    mockLaunchRunner.mockResolvedValue({ run_id: "run-ident", status: "pending" });
    mockOpenRunSocket.mockReturnValue(socket as unknown as WebSocket);

    render(<RecettePage />);
    fireEvent.click(screen.getByRole("button", { name: "Lancer identification" }));
    await waitFor(() =>
      expect(mockLaunchRunner).toHaveBeenCalledWith("identification"),
    );

    feed(socket, identificationFrames as Frame[]);

    // Real capture: 11 agent_result frames, scorecard 11/11 detection 100%.
    expect(screen.getByText("gh-issue-triager")).toBeInTheDocument();
    expect(screen.getByText(/11\/11 agents/)).toBeInTheDocument();
    expect(screen.getByText(/detection rate 100%/)).toBeInTheDocument();
    const rows = screen.getAllByRole("row");
    // 11 agent rows + header row.
    expect(rows.length).toBe(12);
  });

  it("surfaces a launch failure as an alert without crashing", async () => {
    mockLaunchRunner.mockRejectedValue(new Error("API request failed (500) on /runs"));
    render(<RecettePage />);
    fireEvent.click(screen.getByRole("button", { name: "Lancer discovery" }));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("API request failed (500)");
  });
});
