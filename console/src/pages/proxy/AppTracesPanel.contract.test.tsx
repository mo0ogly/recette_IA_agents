/**
 * R16 contract tests for AppTracesPanel (delta-poll rewrite).
 *
 * The fixture in __fixtures__/traces.fixture.json is the REAL delta envelope
 * captured from the backend (recette.api through TestClient with
 * INSPECT_IA_AGENTS_PROXY_DEBUG on), not invented. The api client module is mocked so
 * the panel renders against the exact payload shape the backend returns, and
 * the lazy MonacoJsonViewer is stubbed (Monaco cannot run under jsdom).
 *
 * jsdom performs no layout, so the away-from-tail flow pins the VirtualList
 * scroll metrics with Object.defineProperty and drives fireEvent.scroll (the
 * same technique as VirtualList.test.tsx).
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ProxyTraceResponse } from "../../types/platform";
import tracesFixture from "./__fixtures__/traces.fixture.json";

vi.mock("../../components/MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => (
    <textarea readOnly data-testid="monaco-stub" value={value} />
  ),
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    getProxyTracesDelta: vi.fn(),
    clearProxyTraces: vi.fn(),
    setProxyDebug: vi.fn(),
  };
});

import { clearProxyTraces, getProxyTracesDelta } from "../../api/client";
import AppTracesPanel from "./AppTracesPanel";

const fixture = tracesFixture as ProxyTraceResponse;

function renderPanel(): void {
  render(
    <MemoryRouter initialEntries={["/proxy"]}>
      <AppTracesPanel paused={false} />
    </MemoryRouter>,
  );
}

/** Pin jsdom scroll metrics on the container (no layout engine in jsdom). */
function defineScrollMetrics(
  el: HTMLElement,
  metrics: { scrollTop?: number; scrollHeight?: number; clientHeight?: number },
): void {
  if (metrics.scrollTop !== undefined) {
    Object.defineProperty(el, "scrollTop", { value: metrics.scrollTop, writable: true });
  }
  if (metrics.scrollHeight !== undefined) {
    Object.defineProperty(el, "scrollHeight", { value: metrics.scrollHeight, configurable: true });
  }
  if (metrics.clientHeight !== undefined) {
    Object.defineProperty(el, "clientHeight", { value: metrics.clientHeight, configurable: true });
  }
}

describe("AppTracesPanel (R16 contract, delta poll)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getProxyTracesDelta).mockResolvedValue(fixture);
    vi.mocked(clearProxyTraces).mockResolvedValue({ cleared: true });
  });

  it("renders the trace lines and the count line from the real envelope", async () => {
    renderPanel();
    // The list wrapper renders before the first delta lands: wait for rows.
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() =>
      expect(within(list).getAllByRole("button")).toHaveLength(fixture.traces.length),
    );
    const rows = within(list).getAllByRole("button");
    expect(rows[0]).toHaveTextContent("list_repos");
    expect(rows[0]).toHaveTextContent("ok");
    expect(
      screen.getByText(`${fixture.traces.length} trace(s), 0 echec(s)`),
    ).toBeInTheDocument();
  });

  it("pushes the agent filter server-side (delta query param)", async () => {
    renderPanel();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() => expect(within(list).getAllByRole("button")).toHaveLength(2));
    const filterGroup = screen.getByRole("group", { name: "trace filter" });
    const agentSelect = within(filterGroup).getAllByRole("combobox")[0];
    fireEvent.change(agentSelect, { target: { value: "ci-bot" } });
    // The feed restarts filtered: the SERVER receives the clause, the client
    // no longer narrows locally.
    await waitFor(() =>
      expect(getProxyTracesDelta).toHaveBeenCalledWith(
        expect.objectContaining({ agentId: "ci-bot" }),
      ),
    );
  });

  it("shows the new-traces badge when scrolled away and rows land, and resumes on click", async () => {
    vi.useFakeTimers();
    try {
      const extra = {
        ...fixture.traces[0],
        seq: 3,
        event_id: "EV000000000000000001000003",
      };
      vi.mocked(getProxyTracesDelta).mockImplementation((params) =>
        Promise.resolve(
          params.sinceSeq === undefined
            ? fixture
            : { debug_enabled: true, traces: [extra], last_seq: 3, total: 3, reset: false },
        ),
      );
      renderPanel();
      await vi.advanceTimersByTimeAsync(0); // initial full fetch resolves
      const vlist = screen.getByTestId("proxy-trace-vlist");
      // Leave the tail: 0 + 420 < 2000 - rowHeight.
      defineScrollMetrics(vlist, { scrollTop: 0, scrollHeight: 2000, clientHeight: 420 });
      fireEvent.scroll(vlist);
      // Next 1s tick delivers seq 3 while the user is away.
      await vi.advanceTimersByTimeAsync(1000);
      const badge = screen.getByTestId("proxy-new-traces");
      expect(badge).toHaveTextContent("1 nouvelles traces -- reprendre le suivi");
      fireEvent.click(badge);
      expect(screen.queryByTestId("proxy-new-traces")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders the debug-off banner when the envelope flags tracing disabled", async () => {
    vi.mocked(getProxyTracesDelta).mockResolvedValue({
      debug_enabled: false,
      traces: [],
      last_seq: 0,
      total: 0,
      reset: false,
    });
    renderPanel();
    expect(await screen.findByRole("status")).toHaveTextContent(
      "INSPECT_IA_AGENTS_PROXY_DEBUG",
    );
  });
});
