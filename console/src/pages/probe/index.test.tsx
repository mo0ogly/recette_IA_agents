import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProbePage from "./index";
import { captureProbe, getProbeStatus } from "../../api/client";
import type { ProbeCaptureResult, ProbeStatus } from "../../api/client";
import fixture from "./__fixtures__/probe-capture.fixture.json";

vi.mock("../../api/client", () => ({
  getProbeStatus: vi.fn(),
  captureProbe: vi.fn(),
  getLlmTraces: vi.fn(),
}));

// The Monaco chunk is heavy and worker-bound; stub it so the raw-JSON panel is
// asserted by its value prop without loading the real editor in jsdom.
vi.mock("../../components/MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => <pre data-testid="probe-raw-json">{value}</pre>,
}));

const CONFIGURED: ProbeStatus = {
  configured: true,
  socket_env: "INSPECT_IA_AGENTS_PROBE_SOCKET",
  mode: "replay",
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProbePage", () => {
  it("captures and renders the verdict, false negative and per-surface detail", async () => {
    vi.mocked(getProbeStatus).mockResolvedValue(CONFIGURED);
    vi.mocked(captureProbe).mockResolvedValue(fixture as ProbeCaptureResult);
    render(<ProbePage />);

    const button = await screen.findByTestId("probe-capture-button");
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);

    // Hero verdict reflects the blind spot (ghost seen nowhere).
    expect(await screen.findByTestId("probe-hero")).toHaveTextContent("ANGLE MORT");
    // The false-negative banner names the ghost prominently.
    expect(screen.getByTestId("probe-false-negatives")).toHaveTextContent(
      "ghost-direct-db",
    );
    // The visible agent shows its eBPF-wire capture key.
    expect(
      screen.getByTestId("probe-surface-pr-bot-sdk-ebpf_wire"),
    ).toHaveTextContent("exec:pr-bot:42");
    // The ghost card is marked seen-nowhere.
    expect(screen.getByTestId("probe-agent-ghost-direct-db")).toHaveTextContent(
      "vu nulle part",
    );
  });

  it("labels the replay mode so it is never mistaken for a live eBPF capture", async () => {
    vi.mocked(getProbeStatus).mockResolvedValue(CONFIGURED);
    render(<ProbePage />);

    expect(await screen.findByTestId("probe-mode")).toHaveTextContent("replay");
    expect(screen.getByTestId("probe-replay-note")).toHaveTextContent(
      "PAS une",
    );
  });

  it("disables capture and warns when the broker is not configured", async () => {
    vi.mocked(getProbeStatus).mockResolvedValue({ ...CONFIGURED, configured: false });
    render(<ProbePage />);

    expect(await screen.findByTestId("probe-offline")).toBeInTheDocument();
    expect(screen.getByTestId("probe-capture-button")).toBeDisabled();
  });

  it("surfaces a capture error inline (fail-safe 503)", async () => {
    vi.mocked(getProbeStatus).mockResolvedValue(CONFIGURED);
    vi.mocked(captureProbe).mockRejectedValue(new Error("503 broker unreachable"));
    render(<ProbePage />);

    const button = await screen.findByTestId("probe-capture-button");
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);

    await waitFor(() =>
      expect(screen.getByTestId("probe-error")).toHaveTextContent(
        "503 broker unreachable",
      ),
    );
  });

  it("streams successive windows in live mode and labels them honestly", async () => {
    vi.mocked(getProbeStatus).mockResolvedValue(CONFIGURED);
    vi.mocked(captureProbe).mockResolvedValue(fixture as ProbeCaptureResult);
    render(<ProbePage />);

    const liveBtn = await screen.findByTestId("probe-live-button");
    await waitFor(() => expect(liveBtn).not.toBeDisabled());
    fireEvent.click(liveBtn);

    // The live indicator appears and is labelled as windowed, not per-event.
    const indicator = await screen.findByTestId("probe-live-indicator");
    expect(indicator).toHaveTextContent("live");
    expect(indicator).toHaveTextContent("fenetre");
    // One-shot capture is disabled while live runs (no overlapping captures).
    expect(screen.getByTestId("probe-capture-button")).toBeDisabled();
    // At least one window was captured.
    await waitFor(() => expect(vi.mocked(captureProbe).mock.calls.length).toBeGreaterThan(0));

    // Stopping live re-enables the one-shot capture and clears the indicator.
    fireEvent.click(screen.getByTestId("probe-live-button"));
    await waitFor(() =>
      expect(screen.queryByTestId("probe-live-indicator")).not.toBeInTheDocument(),
    );
  });

  it("shows the raw recording JSON on demand (Monaco panel)", async () => {
    vi.mocked(getProbeStatus).mockResolvedValue(CONFIGURED);
    vi.mocked(captureProbe).mockResolvedValue(fixture as ProbeCaptureResult);
    render(<ProbePage />);

    const button = await screen.findByTestId("probe-capture-button");
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);

    const rawToggle = await screen.findByTestId("probe-raw-toggle");
    expect(screen.queryByTestId("probe-raw-json")).not.toBeInTheDocument();
    fireEvent.click(rawToggle);

    // The raw panel renders the actual recording the probe returned.
    const raw = await screen.findByTestId("probe-raw-json");
    expect(raw.textContent).toContain("recordings");
    expect(raw.textContent).toContain("ghost-direct-db");
  });
});
