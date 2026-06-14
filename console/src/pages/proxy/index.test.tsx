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
    getProxyTraces: vi.fn(),
    clearProxyTraces: vi.fn(),
  };
});

import { clearProxyTraces, getProxyTraces } from "../../api/client";
import ProxyPage from "./index";

const fixture = tracesFixture as ProxyTraceResponse;

function renderPage(): void {
  render(
    <MemoryRouter>
      <ProxyPage />
    </MemoryRouter>,
  );
}

describe("ProxyPage (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getProxyTraces).mockResolvedValue(fixture);
    vi.mocked(clearProxyTraces).mockResolvedValue({ cleared: true });
  });

  it("renders one list item per recorded trace from the real payload", async () => {
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    const items = within(list).getAllByRole("button");
    expect(items).toHaveLength(fixture.traces.length);
    expect(items[0]).toHaveTextContent("list_repos");
    expect(items[0]).toHaveTextContent("ok");
  });

  it("shows the trace JSON in the viewer when a trace is selected", async () => {
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    fireEvent.click(within(list).getAllByRole("button")[0]);
    const viewer = screen.getByTestId("monaco-stub") as HTMLTextAreaElement;
    expect(viewer.value).toContain("side_effect_hash");
    expect(viewer.value).toContain(fixture.traces[0].event_id);
  });

  it("switches to stream mode and serializes every trace as JSONL", async () => {
    renderPage();
    await screen.findByRole("list", { name: "proxy traces" });
    fireEvent.click(screen.getByRole("button", { name: "stream" }));
    const viewer = screen.getByTestId("monaco-stub") as HTMLTextAreaElement;
    expect(viewer.value.split("\n")).toHaveLength(fixture.traces.length);
  });

  it("renders the debug-off banner when tracing is disabled", async () => {
    vi.mocked(getProxyTraces).mockResolvedValue({ debug_enabled: false, traces: [] });
    renderPage();
    expect(await screen.findByRole("status")).toHaveTextContent("INSPECT_IA_AGENTS_PROXY_DEBUG");
  });

  it("clears the buffer through the API on demand", async () => {
    renderPage();
    await screen.findByRole("list", { name: "proxy traces" });
    fireEvent.click(screen.getByRole("button", { name: "Vider le tampon" }));
    await waitFor(() => expect(clearProxyTraces).toHaveBeenCalledTimes(1));
  });

  it("surfaces a load error instead of crashing", async () => {
    vi.mocked(getProxyTraces).mockRejectedValue(new Error("network down"));
    renderPage();
    expect(await screen.findByText(/network down/)).toBeInTheDocument();
  });

  it("filters the list by agent_id", async () => {
    const t0 = fixture.traces[0];
    vi.mocked(getProxyTraces).mockResolvedValue({
      debug_enabled: true,
      traces: [
        { ...t0, seq: 1, agent_id: "agent-a" },
        { ...t0, seq: 2, agent_id: "agent-b" },
      ],
    });
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    expect(within(list).getAllByRole("button")).toHaveLength(2);
    const filterGroup = screen.getByRole("group", { name: "trace filter" });
    const agentSelect = within(filterGroup).getAllByRole("combobox")[0];
    fireEvent.change(agentSelect, { target: { value: "agent-a" } });
    await waitFor(() =>
      expect(within(list).getAllByRole("button")).toHaveLength(1),
    );
    expect(within(list).getByRole("button")).toHaveTextContent("#1");
  });

  it("filters the list by run_id (F3 run <-> traces link)", async () => {
    const t0 = fixture.traces[0];
    vi.mocked(getProxyTraces).mockResolvedValue({
      debug_enabled: true,
      traces: [
        { ...t0, seq: 1, run_id: "run-aaa" },
        { ...t0, seq: 2, run_id: "run-bbb" },
      ],
    });
    renderPage();
    const list = await screen.findByRole("list", { name: "proxy traces" });
    expect(within(list).getAllByRole("button")).toHaveLength(2);
    const filterGroup = screen.getByRole("group", { name: "trace filter" });
    // Selects order: agent_id, target_system, run_id.
    const runSelect = within(filterGroup).getAllByRole("combobox")[2];
    fireEvent.change(runSelect, { target: { value: "run-aaa" } });
    await waitFor(() =>
      expect(within(list).getAllByRole("button")).toHaveLength(1),
    );
    expect(within(list).getByRole("button")).toHaveTextContent("#1");
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
