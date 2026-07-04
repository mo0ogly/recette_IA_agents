/**
 * R16 contract tests for the Proxy debug console page.
 *
 * The fixture in __fixtures__/ was captured from the real backend (recette.api
 * driven through TestClient with INSPECT_IA_AGENTS_PROXY_DEBUG on), not invented. The
 * api client module is mocked so the page renders against the exact payload
 * shape the backend returns, and the lazy MonacoJsonViewer is stubbed (Monaco
 * cannot run under jsdom).
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ProxyTrace, ProxyTraceResponse } from "../../types/platform";
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
    getProxyTraces: vi.fn(),
    getProxyTracesDelta: vi.fn(),
    clearProxyTraces: vi.fn(),
    setProxyDebug: vi.fn(),
    // The page mounts the agent-only LaunchPanel, which loads agents on mount;
    // stub them so the page test does not hit the network and stays deterministic.
    listAgents: vi.fn(() => Promise.resolve([])),
    launchLaneB: vi.fn(),
    // The replay-diff source loads recordings on mount; stub so selecting it in
    // the menu does not hit the network.
    listRecordings: vi.fn(() => Promise.resolve([])),
  };
});

import { clearProxyTraces, getProxyTracesDelta, setProxyDebug } from "../../api/client";
import ProxyPage from "./index";

const fixture = tracesFixture as ProxyTraceResponse;

/** Simulate the SERVER side of the delta endpoint over a fixed dataset: the
 *  panel now pushes every filter clause as a query param, so the mock applies
 *  them (plus the sinceSeq cursor) exactly like the backend does. */
function mockDelta(response: ProxyTraceResponse): void {
  vi.mocked(getProxyTracesDelta).mockImplementation((params) => {
    const filtered = response.traces.filter(
      (t: ProxyTrace) =>
        (params.agentId === undefined || t.agent_id === params.agentId) &&
        (params.target === undefined || t.target_system === params.target) &&
        (params.runId === undefined || t.run_id === params.runId) &&
        (params.outcome === undefined || (t.ok ? "ok" : "fail") === params.outcome) &&
        (params.q === undefined ||
          JSON.stringify(t).toLowerCase().includes(params.q.toLowerCase())) &&
        (params.sinceSeq === undefined || t.seq > params.sinceSeq),
    );
    return Promise.resolve({
      debug_enabled: response.debug_enabled,
      traces: filtered,
      last_seq: filtered.length > 0 ? filtered[filtered.length - 1].seq : (params.sinceSeq ?? 0),
      total: filtered.length,
      reset: false,
    });
  });
}

function renderPage(entries: string[] = ["/proxy"]): void {
  render(
    <MemoryRouter initialEntries={entries}>
      <ProxyPage />
    </MemoryRouter>,
  );
}

describe("ProxyPage (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDelta(fixture);
    vi.mocked(clearProxyTraces).mockResolvedValue({ cleared: true });
  });

  it("renders one list item per recorded trace from the real payload", async () => {
    renderPage();
    // The list wrapper renders before the first delta lands: wait for rows.
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() =>
      expect(within(list).getAllByRole("button")).toHaveLength(fixture.traces.length),
    );
    const items = within(list).getAllByRole("button");
    expect(items[0]).toHaveTextContent("list_repos");
    expect(items[0]).toHaveTextContent("ok");
  });

  it("shows the trace JSON in the viewer when a trace is selected", async () => {
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() =>
      expect(within(list).getAllByRole("button")).toHaveLength(fixture.traces.length),
    );
    fireEvent.click(within(list).getAllByRole("button")[0]);
    const viewer = screen.getByTestId("monaco-stub") as HTMLTextAreaElement;
    expect(viewer.value).toContain("side_effect_hash");
    expect(viewer.value).toContain(fixture.traces[0].event_id);
  });

  it("switches to stream mode and serializes every trace as JSONL", async () => {
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() =>
      expect(within(list).getAllByRole("button")).toHaveLength(fixture.traces.length),
    );
    fireEvent.click(screen.getByRole("button", { name: "stream" }));
    const viewer = screen.getByTestId("monaco-stub") as HTMLTextAreaElement;
    expect(viewer.value.split("\n")).toHaveLength(fixture.traces.length);
  });

  it("renders the debug-off banner when tracing is disabled", async () => {
    mockDelta({ debug_enabled: false, traces: [], last_seq: 0, total: 0, reset: false });
    renderPage();
    expect(await screen.findByRole("status")).toHaveTextContent("INSPECT_IA_AGENTS_PROXY_DEBUG");
  });

  it("toggles proxy debug on from the UI when it is off", async () => {
    mockDelta({ debug_enabled: false, traces: [], last_seq: 0, total: 0, reset: false });
    vi.mocked(setProxyDebug).mockResolvedValue({ debug_enabled: true });
    renderPage();
    const toggle = await screen.findByTestId("proxy-debug-toggle");
    fireEvent.click(toggle);
    await waitFor(() => expect(setProxyDebug).toHaveBeenCalledWith(true));
  });

  it("clears the buffer through the API on demand", async () => {
    renderPage();
    await screen.findByRole("list", { name: "proxy traces" });
    fireEvent.click(screen.getByRole("button", { name: "Vider le tampon" }));
    await waitFor(() => expect(clearProxyTraces).toHaveBeenCalledTimes(1));
  });

  it("surfaces a load error instead of crashing", async () => {
    vi.mocked(getProxyTracesDelta).mockRejectedValue(new Error("network down"));
    renderPage();
    expect(await screen.findByText(/network down/)).toBeInTheDocument();
  });

  it("deep-links the active source via ?source= (renders the wire panel)", async () => {
    render(
      <MemoryRouter initialEntries={["/proxy?source=wire"]}>
        <ProxyPage />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("wire-panel")).toBeInTheDocument();
  });

  it("falls back to the app source on an unknown ?source= value", async () => {
    render(
      <MemoryRouter initialEntries={["/proxy?source=bogus"]}>
        <ProxyPage />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("list", { name: "proxy traces" })).toBeInTheDocument();
  });

  it("filters the list by agent_id (server-side)", async () => {
    const t0 = fixture.traces[0];
    mockDelta({
      debug_enabled: true,
      traces: [
        { ...t0, seq: 1, agent_id: "agent-a" },
        { ...t0, seq: 2, agent_id: "agent-b" },
      ],
      last_seq: 2,
      total: 2,
      reset: false,
    });
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() => expect(within(list).getAllByRole("button")).toHaveLength(2));
    const filterGroup = screen.getByRole("group", { name: "trace filter" });
    const agentSelect = within(filterGroup).getAllByRole("combobox")[0];
    fireEvent.change(agentSelect, { target: { value: "agent-a" } });
    await waitFor(() =>
      expect(within(list).getAllByRole("button")).toHaveLength(1),
    );
    expect(within(list).getByRole("button")).toHaveTextContent("#1");
  });

  it("filters the list by outcome (ok vs fail)", async () => {
    const t0 = fixture.traces[0];
    mockDelta({
      debug_enabled: true,
      traces: [
        { ...t0, seq: 1, ok: true, status_code: 200 },
        { ...t0, seq: 2, ok: false, status_code: 503 },
      ],
      last_seq: 2,
      total: 2,
      reset: false,
    });
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() => expect(within(list).getAllByRole("button")).toHaveLength(2));
    const filterGroup = screen.getByRole("group", { name: "trace filter" });
    // Selects order: agent_id, target_system, run_id, outcome.
    const outcomeSelect = within(filterGroup).getAllByRole("combobox")[3];
    fireEvent.change(outcomeSelect, { target: { value: "fail" } });
    await waitFor(() => expect(within(list).getAllByRole("button")).toHaveLength(1));
    expect(within(list).getByRole("button")).toHaveTextContent("#2");
  });

  it("opens the app traces pre-filtered by free text from ?q= on first render", async () => {
    // The default source is the app-traces panel. Its free-text filter (`q`)
    // is deep-linkable: opening at /proxy?q=open_pr must narrow the list on the
    // first render with no typing. Two distinct traces, only #2 matches.
    const t0 = fixture.traces[0];
    mockDelta({
      debug_enabled: true,
      traces: [
        { ...t0, seq: 1, action_type: "list_repos" },
        { ...t0, seq: 2, action_type: "open_pr" },
      ],
      last_seq: 2,
      total: 2,
      reset: false,
    });
    renderPage(["/proxy?q=open_pr"]);
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() => expect(within(list).getAllByRole("button")).toHaveLength(1));
    expect(within(list).getByRole("button")).toHaveTextContent("#2");
    // The free-text input reflects the URL value (controlled by the query).
    expect(screen.getByTestId("app-filter-text")).toHaveValue("open_pr");
  });

  it("filters the list by run_id (F3 run <-> traces link)", async () => {
    const t0 = fixture.traces[0];
    mockDelta({
      debug_enabled: true,
      traces: [
        { ...t0, seq: 1, run_id: "run-aaa" },
        { ...t0, seq: 2, run_id: "run-bbb" },
      ],
      last_seq: 2,
      total: 2,
      reset: false,
    });
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    await waitFor(() => expect(within(list).getAllByRole("button")).toHaveLength(2));
    const filterGroup = screen.getByRole("group", { name: "trace filter" });
    // Selects order: agent_id, target_system, run_id.
    const runSelect = within(filterGroup).getAllByRole("combobox")[2];
    fireEvent.change(runSelect, { target: { value: "run-aaa" } });
    await waitFor(() =>
      expect(within(list).getAllByRole("button")).toHaveLength(1),
    );
    expect(within(list).getByRole("button")).toHaveTextContent("#1");
  });

  it("exposes the sessions source in the menu and renders its panel when selected", async () => {
    renderPage();
    // The source menu lists every registered source as a button by its label.
    const sourceMenu = await screen.findByRole("group", { name: "source" });
    const sessionsButton = within(sourceMenu).getByText("sessions");
    fireEvent.click(sessionsButton);
    // The sessions panel mounts (it carries data-testid="sessions-panel").
    expect(await screen.findByTestId("sessions-panel")).toBeInTheDocument();
  });

  it("exposes the replay-diff source in the menu and renders its panel when selected", async () => {
    renderPage();
    const sourceMenu = await screen.findByRole("group", { name: "source" });
    fireEvent.click(within(sourceMenu).getByText("replay-diff"));
    expect(await screen.findByTestId("replay-diff-panel")).toBeInTheDocument();
  });

  it("pauses the live poll: no refetch while paused", async () => {
    vi.useFakeTimers();
    try {
      mockDelta({ debug_enabled: true, traces: [], last_seq: 0, total: 0, reset: false });
      renderPage();
      // let the initial fetch resolve
      await vi.advanceTimersByTimeAsync(0);
      const afterMount = vi.mocked(getProxyTracesDelta).mock.calls.length; // >= 1 (initial)
      // click Pause
      fireEvent.click(screen.getByTestId("proxy-pause"));
      await vi.advanceTimersByTimeAsync(5000); // 2+ poll intervals
      expect(vi.mocked(getProxyTracesDelta).mock.calls.length).toBe(afterMount); // no extra fetch
    } finally {
      vi.useRealTimers();
    }
  });

  it("exports the shown traces as a JSONL download", async () => {
    const createUrl = vi.fn(() => "blob:proxy");
    const revokeUrl = vi.fn();
    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    URL.createObjectURL = createUrl;
    URL.revokeObjectURL = revokeUrl;
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    try {
      renderPage();
      await screen.findByRole("list", { name: "proxy traces" });
      fireEvent.click(screen.getByRole("button", { name: "Export JSONL" }));
      expect(createUrl).toHaveBeenCalledTimes(1);
      expect(clickSpy).toHaveBeenCalledTimes(1);
    } finally {
      clickSpy.mockRestore();
      URL.createObjectURL = origCreate;
      URL.revokeObjectURL = origRevoke;
    }
  });
});
