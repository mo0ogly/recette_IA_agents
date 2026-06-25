/**
 * R16 contract gate for the CorrelationPanel: render against a REAL captured
 * payload (__fixtures__/correlation.fixture.json, a live POST /behavior/correlate
 * result) and assert the quadrant grid renders correctly -- in particular the
 * static_blind cell (source-clean, runtime-dirty: the headline research signal),
 * the unresolved block (fail-loud), and the coverage_gaps block.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import CorrelationPanel from "./CorrelationPanel";
import type { CorrelationReport } from "../../api/client";
import * as client from "../../api/client";
import fixture from "./__fixtures__/correlation.fixture.json";

const REAL = fixture as unknown as CorrelationReport;

describe("CorrelationPanel (R16)", () => {
  it("renders the four quadrant labels from a real captured payload", () => {
    render(<CorrelationPanel correlation={REAL} />);
    expect(screen.getByTestId("corr-panel")).toBeInTheDocument();
    expect(screen.getByTestId("quadrant-static_blind")).toBeInTheDocument();
    expect(screen.getByTestId("quadrant-agree_clean")).toBeInTheDocument();
    expect(screen.getByTestId("quadrant-agree_dirty")).toBeInTheDocument();
    expect(screen.getByTestId("quadrant-static_overflag")).toBeInTheDocument();
  });

  it("highlights the static_blind quadrant as alert", () => {
    render(<CorrelationPanel correlation={REAL} />);
    const cell = screen.getByTestId("quadrant-static_blind");
    expect(cell.className).toMatch(/corr-quadrant-alert/);
  });

  it("lists agent_ids inside the static_blind cell", () => {
    render(<CorrelationPanel correlation={REAL} />);
    // pr-bot is the static_blind agent in the real fixture
    expect(screen.getByText("pr-bot")).toBeInTheDocument();
  });

  it("renders unresolved links loud (not hidden)", () => {
    const withGap = {
      ...REAL,
      unresolved: [{ agent_id: "x", reason: "evidence_missing" }],
    };
    render(<CorrelationPanel correlation={withGap as CorrelationReport} />);
    expect(screen.getByText(/evidence_missing/i)).toBeInTheDocument();
  });

  it("renders the provenance line (tool_version + thresholds)", () => {
    render(<CorrelationPanel correlation={REAL} />);
    expect(screen.getByTestId("corr-provenance")).toBeInTheDocument();
    expect(screen.getByTestId("corr-provenance").textContent).toContain("behavior-engine/1");
  });
});

describe("CorrelationPanel -- re-fetch on threshold change", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it("calls correlateBehavior with the new threshold when knob changes", async () => {
    const spy = vi.spyOn(client, "correlateBehavior").mockResolvedValue(REAL);
    render(<CorrelationPanel correlation={REAL} recording={{ recordings: [] }} />);
    const input = screen.getByTestId("corr-threshold-input");
    fireEvent.change(input, { target: { value: "30" } });
    fireEvent.click(screen.getByTestId("corr-run-button"));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    const call = spy.mock.calls[0][0];
    expect(call.thresholds?.runtime_dirty).toBe(30);
  });

  it("auto-fetches corpus mode on mount (no recording) -- P3 populated view", async () => {
    const spy = vi.spyOn(client, "correlateBehavior").mockResolvedValue(REAL);
    render(<CorrelationPanel />);
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    // corpus mode: the request carries NO recording
    expect(spy.mock.calls[0][0].recording).toBeUndefined();
    // the source selector defaults to corpus
    expect((screen.getByTestId("corr-source-select") as HTMLSelectElement).value).toBe("corpus");
  });
});
