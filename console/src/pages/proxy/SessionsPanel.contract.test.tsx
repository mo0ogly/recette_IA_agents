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
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProxyTraceResponse } from "../../types/platform";
import fixture from "./__fixtures__/sessions.fixture.json";
import SessionsPanel from "./SessionsPanel";

vi.mock("../../api/client", () => ({
  getProxyTraces: vi.fn(() => Promise.resolve(fixture as ProxyTraceResponse)),
}));

afterEach(() => vi.clearAllMocks());

describe("SessionsPanel (R16 contract)", () => {
  it("renders one session row per run and no crash on the real payload", async () => {
    render(<SessionsPanel />);
    const list = await screen.findByLabelText("sessions");
    const runs = new Set(
      (fixture as ProxyTraceResponse).traces.map((t) => t.run_id ?? "(no run)"),
    );
    await waitFor(() => {
      expect(within(list).getAllByRole("button").length).toBe(runs.size);
    });
  });

  it("expands an exchange to show the req<->resp pair on demand", async () => {
    render(<SessionsPanel />);
    const list = await screen.findByLabelText("sessions");
    fireEvent.click(within(list).getAllByRole("button")[0]);
    const timeline = await screen.findByLabelText("session exchanges");
    const firstExchange = within(timeline).getAllByRole("button")[0];
    fireEvent.click(firstExchange);
    expect(await screen.findByTestId("exchange-intent")).toBeInTheDocument();
    expect(screen.getByTestId("exchange-response")).toBeInTheDocument();
  });
});
