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
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProxyTraceResponse, WireFlowResponse } from "../../types/platform";
import fixture from "./__fixtures__/sessions.fixture.json";
import wireFixture from "./__fixtures__/sessions-wire.fixture.json";
import SessionsPanel from "./SessionsPanel";

// The wire fixture's flow shares run_id + side_effect_hash with the FIRST trace
// (seq 5) of this run, so its first exchange carries the matched wire flow.
const RUN_WITH_WIRE = "1e9b7889ec614c45894e8c855ea72543";

vi.mock("../../api/client", () => ({
  getProxyTraces: vi.fn(() => Promise.resolve(fixture as ProxyTraceResponse)),
  getWireFlows: vi.fn(() => Promise.resolve(wireFixture as WireFlowResponse)),
}));

// Stub Monaco so its rendered value is assertable in jsdom.
vi.mock("../../components/MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => <pre data-testid="monaco-stub">{value}</pre>,
}));

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

  it("preselects the run named in ?run= without a click", async () => {
    const run = (fixture as ProxyTraceResponse).traces[0].run_id!;
    renderPanel({}, `/?run=${run}`);
    expect(await screen.findByLabelText("session exchanges")).toBeInTheDocument();
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
