/**
 * Contract gate for PrecisionRecallPanel: drive it with a REAL-shaped bench
 * payload (__fixtures__/bench.fixture.json, a POST /probe/bench result) and
 * assert the scorecard renders — the recall headline, the TP/FN/FP counts, the
 * per-endpoint verdict badges (the FN "ghost" row is the load-bearing signal),
 * and the partial-coverage warning. The client call is mocked; pct/verdictLabel
 * stay real so the formatting is exercised end to end.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import PrecisionRecallPanel from "./PrecisionRecallPanel";
import type { ProbeBenchResult } from "./benchModel";
import * as bench from "./benchModel";
import fixture from "./__fixtures__/bench.fixture.json";

const REAL = fixture as unknown as ProbeBenchResult;

describe("PrecisionRecallPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  async function runWith(result: ProbeBenchResult): Promise<void> {
    vi.spyOn(bench, "runProbeBench").mockResolvedValue(result);
    render(<PrecisionRecallPanel />);
    fireEvent.change(screen.getByTestId("bench-agents"), { target: { value: "pr-bot" } });
    fireEvent.click(screen.getByTestId("bench-run"));
    await waitFor(() => expect(screen.getByTestId("bench-metrics")).toBeInTheDocument());
  }

  it("renders recall/precision/F1 and TP/FN/FP from the payload", async () => {
    await runWith(REAL);
    const metrics = screen.getByTestId("bench-metrics");
    expect(metrics).toHaveTextContent("50%"); // recall / precision / f1
    expect(metrics).toHaveTextContent("TP");
    expect(metrics).toHaveTextContent("FN (ghost)");
  });

  it("shows one row per endpoint with the right verdict badge", async () => {
    await runWith(REAL);
    expect(screen.getByTestId("bench-row-104.18.2.1:443")).toHaveTextContent("detecte");
    expect(screen.getByTestId("bench-row-203.0.113.9:443")).toHaveTextContent("manque");
    expect(screen.getByTestId("bench-row-8.8.8.8:53")).toHaveTextContent("probe seul");
  });

  it("labels the FN ghost row with its wire host + JA3", async () => {
    await runWith(REAL);
    const ghost = screen.getByTestId("bench-row-203.0.113.9:443");
    expect(ghost).toHaveTextContent("evil.exfil.net");
    expect(ghost).toHaveTextContent("deadbeef");
  });

  it("surfaces partial wire coverage (flows without an L3/L4 IP)", async () => {
    await runWith(REAL);
    expect(screen.getByTestId("bench-coverage")).toHaveTextContent("1 flux sans IP L3/L4");
  });

  it("requires at least one agent before running", async () => {
    render(<PrecisionRecallPanel />);
    fireEvent.click(screen.getByTestId("bench-run"));
    await waitFor(() => expect(screen.getByTestId("bench-error")).toBeInTheDocument());
  });

  it("shows 'n/a' when a rate is undefined (no detections)", async () => {
    await runWith({
      recording_status: "ok",
      wire_flows_total: 1,
      report: {
        tp: 0, fp: 0, fn: 1,
        precision: null, recall: 0, f1: null,
        wire_endpoints: 1, probe_endpoints: 0, wire_flows_without_ip: 0,
        endpoints: [
          { endpoint: "1.1.1.1:443", ip: "1.1.1.1", port: 443, in_wire: true, in_probe: false, verdict: "fn", host: null, ja3: null },
        ],
      },
    });
    expect(screen.getByTestId("bench-metrics")).toHaveTextContent("n/a");
  });
});
