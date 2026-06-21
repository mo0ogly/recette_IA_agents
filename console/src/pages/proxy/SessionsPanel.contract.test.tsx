/**
 * R16 contract tests for the sessions panel.
 *
 * The fixture in __fixtures__/sessions.fixture.json carries two interleaved
 * runs (real ProxyTraceResponse shape). The api client is mocked so the panel
 * renders against the exact payload the backend returns. Covers the grouping
 * (one session row per run) and the progressive-disclosure expand of an
 * exchange into its req<->resp pair. Uses fireEvent (sibling-test convention):
 * @testing-library/user-event is not a dependency of this console.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getReconcile, getRunEvents } from "../../api/client";
import type {
  ProxyTraceResponse,
  ReconcileReport,
  RunEvent,
  WireFlowResponse,
} from "../../types/platform";
import fixture from "./__fixtures__/sessions.fixture.json";
import wireFixture from "./__fixtures__/sessions-wire.fixture.json";
import SessionsPanel from "./SessionsPanel";

// The wire fixture's flow shares run_id + side_effect_hash with the FIRST trace
// (seq 5) of this run, so its first exchange carries the matched wire flow.
const RUN_WITH_WIRE = "1e9b7889ec614c45894e8c855ea72543";
// The non-null side_effect_hash of that first exchange (trace seq 5). A reconcile
// bypass_flow carrying this hash means the exchange is a non-mediated (ghost) path.
const GHOST_HASH = "f8e2690c2ca18f35a54e2f5a11351d03091cde454fa097427b3b60c94cf19db9";

const okReconcile: ReconcileReport = {
  run_id: RUN_WITH_WIRE,
  ok: true,
  bypass_flows: [],
  audited_run_ids: [],
  strict: true,
};

const ghostReconcile: ReconcileReport = {
  run_id: RUN_WITH_WIRE,
  ok: false,
  bypass_flows: [
    {
      ...(wireFixture as WireFlowResponse).flows[0],
      side_effect_hash: GHOST_HASH,
      bypass_reason: "no_audit_event",
    },
  ],
  audited_run_ids: [],
  strict: true,
};

// Ordered tool_call decisions for RUN_WITH_WIRE's three exchanges (real wire
// shape: type + nested data.{name,args}). Order matches the fixture run's
// exchanges (list_repos, read_repo, open_issue) so the i-th decision folds onto
// the i-th exchange.
const runEvents: RunEvent[] = [
  { seq: 1, type: "step", data: { index: 0, decision: { text: "enumerate repos" } } },
  { seq: 2, type: "tool_call", data: { index: 0, name: "list_repos", args: { resource: "acme/x" } } },
  { seq: 3, type: "step", data: { index: 1, decision: { text: "read the target" } } },
  { seq: 4, type: "tool_call", data: { index: 1, name: "read_repo", args: { resource: "acme/x" } } },
  { seq: 5, type: "tool_call", data: { index: 2, name: "open_issue", args: { resource: "acme/x" } } },
];

vi.mock("../../api/client", () => ({
  getProxyTraces: vi.fn(() => Promise.resolve(fixture as ProxyTraceResponse)),
  getWireFlows: vi.fn(() => Promise.resolve(wireFixture as WireFlowResponse)),
  getReconcile: vi.fn(() => Promise.resolve(okReconcile)),
  getRunEvents: vi.fn(() => Promise.resolve(runEvents)),
}));

// Stub Monaco so its rendered value is assertable in jsdom.
vi.mock("../../components/MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => <pre data-testid="monaco-stub">{value}</pre>,
}));

// jsdom has no clipboard; stub it so the copy-curl path runs.
beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
});

afterEach(() => vi.clearAllMocks());

const renderPanel = (props = {}, route = "/") =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <SessionsPanel {...props} />
    </MemoryRouter>,
  );

describe("SessionsPanel (R16 contract)", () => {
  it("renders one session row per run and no crash on the real payload", async () => {
    renderPanel();
    const list = await screen.findByLabelText("sessions");
    const runs = new Set(
      (fixture as ProxyTraceResponse).traces.map((t) => t.run_id ?? "(no run)"),
    );
    await waitFor(() => {
      expect(within(list).getAllByRole("button").length).toBe(runs.size);
    });
  });

  it("expands an exchange to show the req<->resp pair on demand", async () => {
    renderPanel();
    const list = await screen.findByLabelText("sessions");
    fireEvent.click(within(list).getAllByRole("button")[0]);
    const timeline = await screen.findByLabelText("session exchanges");
    const firstExchange = within(timeline).getAllByRole("button")[0];
    fireEvent.click(firstExchange);
    expect(await screen.findByTestId("exchange-intent")).toBeInTheDocument();
    expect(screen.getByTestId("exchange-response")).toBeInTheDocument();
  });

  it("shows a wire badge on an exchange and opens the raw bytes in Monaco", async () => {
    renderPanel({}, `/?run=${RUN_WITH_WIRE}`);
    const timeline = await screen.findByLabelText("session exchanges");
    fireEvent.click(within(timeline).getAllByRole("button")[0]); // expand first exchange
    const wireBtn = await screen.findByTestId("exchange-wire-btn");
    fireEvent.click(wireBtn);
    expect(await screen.findByText(/event_id/)).toBeInTheDocument(); // raw request bytes
    // Prove the wire OBJECT is rendered (not just the serialized request_body
    // string): a top-level wire field from the fixture (path) must be present.
    expect(screen.getByText(/\/github\/execute/)).toBeInTheDocument();
  });

  it("copies a curl command for an exchange with a matched wire flow", async () => {
    renderPanel({}, `/?run=${RUN_WITH_WIRE}`);
    const timeline = await screen.findByLabelText("session exchanges");
    fireEvent.click(within(timeline).getAllByRole("button")[0]); // expand first exchange
    const copy = await screen.findByTestId("exchange-copy-curl");
    fireEvent.click(copy);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining("curl -X"),
    );
  });

  it("preselects the run named in ?run= without a click", async () => {
    const run = (fixture as ProxyTraceResponse).traces[0].run_id!;
    renderPanel({}, `/?run=${run}`);
    expect(await screen.findByLabelText("session exchanges")).toBeInTheDocument();
  });

  it("marks an exchange ghost / non-mediated when reconcile flags its hash as a bypass", async () => {
    vi.mocked(getReconcile).mockResolvedValue(ghostReconcile);
    renderPanel({}, `/?run=${RUN_WITH_WIRE}`);
    const timeline = await screen.findByLabelText("session exchanges");
    fireEvent.click(within(timeline).getAllByRole("button")[0]); // expand first exchange
    expect(await screen.findByTestId("exchange-ghost")).toBeInTheDocument();
  });

  it("shows no ghost badge when reconcile reports no bypass flows", async () => {
    vi.mocked(getReconcile).mockResolvedValue(okReconcile);
    renderPanel({}, `/?run=${RUN_WITH_WIRE}`);
    const timeline = await screen.findByLabelText("session exchanges");
    fireEvent.click(within(timeline).getAllByRole("button")[0]); // expand first exchange
    await screen.findByTestId("exchange-intent");
    expect(screen.queryByTestId("exchange-ghost")).not.toBeInTheDocument();
  });

  it("shows the DECIDE altitude (the why) for an exchange from the run's events", async () => {
    renderPanel({}, `/?run=${RUN_WITH_WIRE}`);
    const timeline = await screen.findByLabelText("session exchanges");
    fireEvent.click(within(timeline).getAllByRole("button")[0]); // expand first exchange
    const decision = await screen.findByTestId("exchange-decision");
    expect(decision).toHaveTextContent("list_repos");
    expect(decision).toHaveTextContent("enumerate repos");
  });

  it("renders gracefully (no decision, no crash) when getRunEvents rejects", async () => {
    vi.mocked(getRunEvents).mockRejectedValue(new Error("events unavailable"));
    renderPanel({}, `/?run=${RUN_WITH_WIRE}`);
    const timeline = await screen.findByLabelText("session exchanges");
    fireEvent.click(within(timeline).getAllByRole("button")[0]); // expand first exchange
    await screen.findByTestId("exchange-intent");
    expect(screen.queryByTestId("exchange-decision")).not.toBeInTheDocument();
  });

  it("reports status up via onStatus without looping on a stable ref", async () => {
    const onStatus = vi.fn();
    renderPanel({ onStatus });
    await screen.findByLabelText("sessions");
    await waitFor(() => expect(onStatus).toHaveBeenCalled());
    const callsAfterLoad = onStatus.mock.calls.length;
    // No state change -> the effect must not keep firing (loop guard).
    await new Promise((r) => setTimeout(r, 50));
    expect(onStatus.mock.calls.length).toBe(callsAfterLoad);
  });
});
