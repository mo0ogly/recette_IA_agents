/**
 * R16 contract tests for the wire<->audit reconciliation panel.
 *
 * The fixture in __fixtures__/reconcile.fixture.json was captured from the real
 * backend (recette.api via TestClient: POST /proxy/wire x2 then GET
 * /proxy/reconcile), not invented. The api client is mocked so the panel renders
 * against the exact payload shape the backend returns. Covers BOTH verdict
 * states: bypass detected (ok=false, a row per unmediated flow) and clean
 * (ok=true, no bypass).
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReconcileReport } from "../../types/platform";
import reconcileFixture from "./__fixtures__/reconcile.fixture.json";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, getReconcile: vi.fn(), raiseReconcile: vi.fn() };
});

import { getReconcile, raiseReconcile } from "../../api/client";
import ReconcilePanel from "./ReconcilePanel";

const fixture = reconcileFixture as ReconcileReport;

describe("ReconcilePanel (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getReconcile).mockResolvedValue(fixture);
    vi.mocked(raiseReconcile).mockResolvedValue({ raised: 1, event_ids: ["EV-1"] });
  });

  it("renders the captured bypass report without crashing", async () => {
    render(<ReconcilePanel />);
    // The fixture is a real ok=false report with one :9113 honeypot flow.
    expect(await screen.findByTestId("reconcile-bypass")).toBeInTheDocument();
    const table = screen.getByLabelText("bypass flows");
    const rows = within(table).getAllByTestId("reconcile-row");
    expect(rows).toHaveLength(fixture.bypass_flows.length);
    expect(table).toHaveTextContent("127.0.0.1:9113");
    expect(table).toHaveTextContent("/shadow_db/write");
  });

  it("raises the bypass to the audit log on demand", async () => {
    render(<ReconcilePanel />);
    fireEvent.click(await screen.findByTestId("reconcile-raise"));
    await waitFor(() => expect(raiseReconcile).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId("reconcile-raise-msg")).toHaveTextContent("1 evenement");
  });

  it("does not offer the raise button on a clean run", async () => {
    vi.mocked(getReconcile).mockResolvedValue({
      run_id: null,
      ok: true,
      bypass_flows: [],
      audited_run_ids: [],
    });
    render(<ReconcilePanel />);
    await screen.findByTestId("reconcile-ok");
    expect(screen.queryByTestId("reconcile-raise")).not.toBeInTheDocument();
  });

  it("toggling strict re-queries with the phase-3 join", async () => {
    render(<ReconcilePanel />);
    await screen.findByTestId("reconcile-bypass");
    const toggle = within(screen.getByTestId("reconcile-strict-toggle")).getByRole("checkbox");
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(vi.mocked(getReconcile)).toHaveBeenCalledWith(undefined, true),
    );
  });

  it("renders the bypass_reason column from a strict report", async () => {
    vi.mocked(getReconcile).mockResolvedValue({
      run_id: null,
      ok: false,
      strict: true,
      audited_run_ids: [],
      bypass_flows: [
        { ...fixture.bypass_flows[0], bypass_reason: "no_audit_event" },
      ] as ReconcileReport["bypass_flows"],
    });
    render(<ReconcilePanel />);
    const table = await screen.findByLabelText("bypass flows");
    expect(table).toHaveTextContent("no_audit_event");
  });

  it("shows the clean state when no flow is unmediated", async () => {
    vi.mocked(getReconcile).mockResolvedValue({
      run_id: null,
      ok: true,
      bypass_flows: [],
      audited_run_ids: ["ghost-run-1"],
    });
    render(<ReconcilePanel />);
    expect(await screen.findByTestId("reconcile-ok")).toBeInTheDocument();
    expect(screen.getByTestId("reconcile-clean")).toBeInTheDocument();
    expect(screen.queryByLabelText("bypass flows")).not.toBeInTheDocument();
    // The audit-view context is surfaced.
    expect(screen.getByTestId("reconcile-audited")).toHaveTextContent("ghost-run-1");
  });

  it("surfaces a fetch error instead of crashing", async () => {
    vi.mocked(getReconcile).mockRejectedValue(new Error("boom"));
    render(<ReconcilePanel />);
    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
  });
});
