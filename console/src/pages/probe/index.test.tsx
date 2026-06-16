import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProbePage from "./index";
import { captureProbe, getProbeStatus } from "../../api/client";
import type { ProbeCaptureResult, ProbeStatus } from "../../api/client";
import fixture from "./__fixtures__/probe-capture.fixture.json";

vi.mock("../../api/client", () => ({
  getProbeStatus: vi.fn(),
  captureProbe: vi.fn(),
}));

const CONFIGURED: ProbeStatus = { configured: true, socket_env: "INSPECT_IA_AGENTS_PROBE_SOCKET" };

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
});
