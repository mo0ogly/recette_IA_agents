/**
 * R16 contract gate for the behavioral-analysis wave view: render against a REAL
 * captured payload (__fixtures__/behavior-wave.fixture.json, a live POST
 * /behavior/wave result) and assert the analyst's report renders -- the per-agent
 * DIVERGENT verdict, the behavioral score, the standards-tagged findings, and the
 * research metrics block (separation AUC).
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import BehaviorWavePanel, { BehaviorReportView } from "./BehaviorWavePanel";
import type { BehaviorWaveResult } from "../../api/client";
import * as client from "../../api/client";
import fixture from "./__fixtures__/behavior-wave.fixture.json";

const REAL = fixture as unknown as BehaviorWaveResult;

describe("BehaviorReportView (R16)", () => {
  it("renders the wave report from a real captured payload", () => {
    render(<BehaviorReportView result={REAL} />);
    expect(screen.getByTestId("behavior-result")).toBeInTheDocument();
    const leak = REAL.report.agents.find((a) => a.agent_id === "leak-bot")!;
    expect(screen.getByTestId("bw-verdict-leak-bot")).toHaveTextContent("DIVERGENT");
    // a standards-tagged finding renders
    expect(screen.getByText(leak.findings[0].log)).toBeInTheDocument();
    // the metrics block (this fixture carries ground-truth)
    expect(screen.getByTestId("bw-metrics")).toBeInTheDocument();
    expect(screen.getByText(/separation AUC/)).toBeInTheDocument();
  });
});

describe("BehaviorWavePanel", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing without a recording", () => {
    const { container } = render(<BehaviorWavePanel recording={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("runs a wave and renders the result", async () => {
    vi.spyOn(client, "runBehaviorWave").mockResolvedValue(REAL);
    render(<BehaviorWavePanel recording={{ recordings: [] }} />);
    expect(screen.getByTestId("behavior-wave-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Run wave"));
    await waitFor(() => expect(screen.getByTestId("behavior-result")).toBeInTheDocument());
    expect(client.runBehaviorWave).toHaveBeenCalledTimes(1);
  });

  it("sends cohort.discovery=flagged when Flagged is selected", async () => {
    const mockRun = vi.spyOn(client, "runBehaviorWave").mockResolvedValue(REAL);
    render(<BehaviorWavePanel recording={{ recordings: [] }} />);
    fireEvent.change(screen.getByTestId("bw-cohort-select"), { target: { value: "flagged" } });
    fireEvent.click(screen.getByText("Run wave"));
    await waitFor(() => expect(mockRun).toHaveBeenCalledTimes(1));
    const profile = mockRun.mock.calls[0][1] as client.BehaviorProfile;
    expect(profile.cohort?.discovery).toBe("flagged");
  });
});
