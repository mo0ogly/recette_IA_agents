/**
 * R16 contract tests for the wire-overlay panel (delta-poll rewrite).
 *
 * The fixture in __fixtures__/wire.fixture.json was captured from the real
 * backend (recette.api driven through TestClient: POST /proxy/wire then GET
 * /proxy/wire), not invented. The api client is mocked so the panel renders
 * against the exact payload shape the backend returns; the mock simulates the
 * SERVER side of the delta endpoint (the panel now pushes every filter clause
 * as a query param, so the mock applies them plus the sinceSeq cursor exactly
 * like the backend does). Covers both overlay states (disabled -> hint banner;
 * enabled -> proxy URL shown) and the select-and-inspect flow.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WireFlow, WireFlowResponse } from "../../types/platform";
import wireFixture from "./__fixtures__/wire.fixture.json";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    getWireFlowsDelta: vi.fn(),
    clearWireFlows: vi.fn(),
    controlWireOverlay: vi.fn(),
  };
});

import { clearWireFlows, controlWireOverlay, getWireFlowsDelta } from "../../api/client";
import WirePanel from "./WirePanel";

const fixture = wireFixture as WireFlowResponse;

/** Simulate the SERVER side of the wire delta endpoint over a fixed dataset:
 *  apply every clause (host/method/status/run/q) plus the sinceSeq cursor,
 *  mirroring the backend's filtered-delta contract. */
function mockWireDelta(response: WireFlowResponse): void {
  vi.mocked(getWireFlowsDelta).mockImplementation((params) => {
    const filtered = response.flows.filter(
      (f: WireFlow) =>
        (params.host === undefined || f.host === params.host) &&
        (params.method === undefined ||
          f.method.toUpperCase() === params.method.toUpperCase()) &&
        (params.status === undefined || f.status_code === params.status) &&
        (params.runId === undefined || f.run_id === params.runId) &&
        (params.q === undefined ||
          `${f.path}\n${f.request_body}\n${f.response_body}`
            .toLowerCase()
            .includes(params.q.toLowerCase())) &&
        (params.sinceSeq === undefined || f.seq > params.sinceSeq),
    );
    return Promise.resolve({
      enabled: response.enabled,
      proxy_url: response.proxy_url,
      flows: filtered,
      last_seq:
        filtered.length > 0 ? filtered[filtered.length - 1].seq : (params.sinceSeq ?? 0),
      total: filtered.length,
      reset: false,
    });
  });
}

/**
 * WirePanel reads its filter clauses from the URL query string
 * (useSearchParams), so every render needs a router. `entries` lets a test
 * open the panel pre-filtered (deep-link) on first render.
 */
function renderWire(entries: string[] = ["/proxy"]): void {
  render(
    <MemoryRouter initialEntries={entries}>
      <WirePanel paused={false} />
    </MemoryRouter>,
  );
}

/**
 * The per-flow SELECT buttons (one per flow). Each virtualized row carries two
 * buttons -- the select button (`proxy-list-item`) and a "comparer" button --
 * so the flow count is the count of select buttons, queried by class rather
 * than the raw button role.
 */
function selectButtons(list: HTMLElement): HTMLElement[] {
  return within(list)
    .getAllByRole("button")
    .filter((b) => b.classList.contains("proxy-list-item"));
}

describe("WirePanel (R16 contract, delta poll)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWireDelta(fixture);
    vi.mocked(clearWireFlows).mockResolvedValue({ cleared: true });
    // jsdom has no Blob URL plumbing; stub it so the export download path runs.
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => "blob:x");
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();
    // jsdom has no clipboard; stub it so the copy-curl path runs.
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
  });

  it("renders the captured flows without crashing", async () => {
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    // The fixture has two flows; both lines show up once the delta lands.
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    expect(screen.getByText(/2 flux, 1 echec/)).toBeInTheDocument();
  });

  it("shows the disabled banner when the overlay is off and no flows arrived", async () => {
    // enabled=false (no INSPECT_IA_AGENTS_WIRE_PROXY in the capture env) AND an
    // empty buffer: the panel must explain how to enable it, not show a bare
    // empty list as a steady state.
    mockWireDelta({
      enabled: false,
      proxy_url: null,
      flows: [],
      last_seq: 0,
      total: 0,
      reset: false,
    });
    renderWire();
    expect(await screen.findByTestId("wire-disabled")).toBeInTheDocument();
  });

  it("hides the how-to-enable banner when flows arrived despite the overlay being off", async () => {
    // Flows can reach the buffer via the transport-route registry even when
    // INSPECT_IA_AGENTS_WIRE_PROXY is unset (enabled=false). The captured fixture is
    // exactly that case: enabled=false WITH real flows. The how-to-enable
    // banner must yield to the actual data, not sit on top of it.
    renderWire();
    // The list container renders before the first fetch lands: wait for rows.
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    expect(screen.queryByText(/wire up/)).toBeNull();
    expect(screen.queryByText(/INSPECT_IA_AGENTS_WIRE_PROXY/)).toBeNull();
    expect(screen.queryByTestId("wire-disabled")).toBeNull();
  });

  it("shows the how-to-enable banner when the overlay is off and there are no flows", async () => {
    mockWireDelta({
      enabled: false,
      proxy_url: null,
      flows: [],
      last_seq: 0,
      total: 0,
      reset: false,
    });
    renderWire();
    expect(await screen.findByTestId("wire-disabled")).toBeInTheDocument();
  });

  it("shows the proxy URL when the overlay is enabled", async () => {
    mockWireDelta({
      ...fixture,
      enabled: true,
      proxy_url: "http://127.0.0.1:8083",
    });
    renderWire();
    const url = await screen.findByTestId("wire-proxy-url");
    expect(url).toHaveTextContent("http://127.0.0.1:8083");
    expect(screen.queryByTestId("wire-disabled")).not.toBeInTheDocument();
  });

  it("inspects a selected flow's request and response bodies", async () => {
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    fireEvent.click(selectButtons(list)[0]);
    const detail = await screen.findByTestId("wire-detail");
    // The first fixture flow is the open_pr request -> 201 success body.
    expect(detail).toHaveTextContent("open_pr");
    expect(detail).toHaveTextContent('"number":42');
    expect(detail).toHaveTextContent("201");
  });

  it("pretty-prints a JSON body on toggle and shows a UTF-8 size indicator", async () => {
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    fireEvent.click(selectButtons(list)[0]);
    const detail = await screen.findByTestId("wire-detail");
    // A byte-size indicator (number followed by " o") is shown for the bodies.
    expect(detail).toHaveTextContent(/\d+ o/);
    // Compact JSON request_body: pretty toggle reformats it with indentation.
    fireEvent.click(screen.getByTestId("wire-pretty-toggle"));
    await waitFor(() => expect(detail.textContent).toMatch(/\n {2}/));
  });

  it("copies a curl command for the selected flow", async () => {
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    fireEvent.click(selectButtons(list)[0]);
    const copy = await screen.findByTestId("wire-copy-curl");
    fireEvent.click(copy);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining("curl -X"),
    );
  });

  it("starts the overlay and surfaces the honest next_step note", async () => {
    // Overlay off in the fixture (enabled=false): the toggle must request "up".
    vi.mocked(controlWireOverlay).mockResolvedValue({
      ok: true,
      action: "up",
      returncode: 0,
      // Mirrors the real POST /proxy/wire/overlay payload (recette/api/routers/
      // proxy.py): route selection is runtime, only real-HTTPS needs a restart.
      next_step:
        "choisir la route de transport 'Wire (mitmproxy)' dans le selecteur "
        + "(sans redemarrage, runs suivants); HTTPS reel: faire confiance au CA "
        + "(./recette.sh wire ca -> INSPECT_IA_AGENTS_WIRE_CA) puis ./recette.sh api restart",
    });
    renderWire();
    const toggle = await screen.findByTestId("wire-overlay-toggle");
    fireEvent.click(toggle);
    await waitFor(() => expect(controlWireOverlay).toHaveBeenCalledWith("up"));
    expect(
      await screen.findByText(/choisir la route de transport 'Wire \(mitmproxy\)'/),
    ).toBeInTheDocument();
  });

  it("clears the buffer on demand and restarts the feed", async () => {
    renderWire();
    await screen.findByLabelText("wire flows");
    fireEvent.click(screen.getByText("Vider le tampon"));
    await waitFor(() => expect(clearWireFlows).toHaveBeenCalledTimes(1));
    // The feed restarts full after a clear: a fresh cursorless delta call.
    await waitFor(() =>
      expect(getWireFlowsDelta).toHaveBeenLastCalledWith(
        expect.objectContaining({ sinceSeq: undefined }),
      ),
    );
  });

  it("narrows the flow list when a text filter matches only some flows (server-side)", async () => {
    // The fixture has two flows on the same host/method/path; only flow #1's
    // request_body carries the "open_pr" token, so it is the only match.
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));

    const text = screen.getByTestId("wire-filter-text");
    fireEvent.change(text, { target: { value: "open_pr" } });

    await waitFor(() =>
      expect(selectButtons(list).length).toBeLessThan(fixture.flows.length),
    );
    expect(selectButtons(list)).toHaveLength(1);
  });

  it("pushes the host filter server-side (delta query param)", async () => {
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    const filterGroup = screen.getByRole("group", { name: "wire filter" });
    const hostSelect = within(filterGroup).getAllByRole("combobox")[0];
    fireEvent.change(hostSelect, { target: { value: "127.0.0.1" } });
    // The feed restarts filtered: the SERVER receives the clause, the client
    // no longer narrows locally.
    await waitFor(() =>
      expect(getWireFlowsDelta).toHaveBeenCalledWith(
        expect.objectContaining({ host: "127.0.0.1" }),
      ),
    );
  });

  it("flags a body clamped by the backend (truncation marker) and not a normal body", async () => {
    // The detector keys off the literal marker appended by wire.py _clamp_body,
    // not a numeric length, so a body ending in the marker is flagged truncated
    // while a normal short body is not (zero false-positive).
    mockWireDelta({
      enabled: false,
      proxy_url: null,
      flows: [
        {
          ...fixture.flows[0],
          seq: 7,
          request_body: '{"big":"x"}...[truncated]',
        },
      ],
      last_seq: 7,
      total: 1,
      reset: false,
    });
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(1));
    fireEvent.click(selectButtons(list)[0]);
    await screen.findByTestId("wire-detail");
    expect(screen.getByTestId("wire-req-truncated")).toBeInTheDocument();
  });

  it("does not flag a normal (non-marker) body as truncated", async () => {
    // The first fixture flow carries a short, un-clamped request_body, so no
    // truncation marker -> no truncated badge.
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    fireEvent.click(selectButtons(list)[0]);
    await screen.findByTestId("wire-detail");
    expect(screen.queryByTestId("wire-req-truncated")).toBeNull();
    expect(screen.queryByTestId("wire-resp-truncated")).toBeNull();
  });

  it("shows the per-exchange latency in the detail pane when duration_ms is set", async () => {
    // duration_ms is OPS metadata on the wire view only (never a judge input,
    // I4). When present, the detail pane surfaces it as a latency line.
    mockWireDelta({
      enabled: false,
      proxy_url: null,
      flows: [{ ...fixture.flows[0], seq: 5, duration_ms: 42 }],
      last_seq: 5,
      total: 1,
      reset: false,
    });
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(1));
    fireEvent.click(selectButtons(list)[0]);
    const detail = await screen.findByTestId("wire-detail");
    expect(detail).toHaveTextContent("42 ms");
  });

  it("exports the shown flows as HAR", async () => {
    renderWire();
    await screen.findByLabelText("wire flows");
    fireEvent.click(screen.getByTestId("wire-export-har"));
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it("opens pre-filtered by free text from ?q= on first render (deep-link)", async () => {
    // Both fixture flows share host/method/path; only flow #1 carries the
    // "open_pr" token in its request_body. Opening at ?q=open_pr must narrow
    // the list to that single flow WITHOUT any typing (the clause rides the
    // very first delta call).
    renderWire(["/proxy?source=wire&q=open_pr"]);
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(1));
    // The free-text input reflects the URL value (controlled by the query).
    expect(screen.getByTestId("wire-filter-text")).toHaveValue("open_pr");
  });

  it("opens pre-filtered by host from ?host= on first render (deep-link)", async () => {
    // Both fixture flows are on host 127.0.0.1, so ?host=127.0.0.1 keeps both
    // and proves the host clause is driven by the URL. A non-matching host
    // empties the list.
    renderWire(["/proxy?source=wire&host=127.0.0.1"]);
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    expect(screen.getByDisplayValue("127.0.0.1")).toBeInTheDocument();
    // And the clause was pushed server-side on the first fetch.
    expect(getWireFlowsDelta).toHaveBeenCalledWith(
      expect.objectContaining({ host: "127.0.0.1" }),
    );
  });

  it("empties the list when ?host= matches no flow (deep-link)", async () => {
    renderWire(["/proxy?source=wire&host=does-not-exist"]);
    await screen.findByLabelText("wire flows");
    await waitFor(() =>
      expect(screen.getByText("aucun flux")).toBeInTheDocument(),
    );
  });

  it("diffs two wire flows side by side (select A, compare B)", async () => {
    // The fixture has two flows that differ (seq/status/bodies): selecting flow
    // #1 then comparing against flow #2 renders a side-by-side line diff with at
    // least one differing line (e.g. the seq or the status_code).
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    // Select flow A (first list-item button is its select button).
    fireEvent.click(selectButtons(list)[0]);
    await screen.findByTestId("wire-detail");
    // Compare against flow B (#2) via its per-row compare button.
    fireEvent.click(screen.getByTestId("wire-compare-2"));

    const diff = await screen.findByTestId("wire-diff");
    expect(diff).toBeInTheDocument();
    // A changed line must be present: flow #2's seq value (2) appears only on
    // the right side of a differing row.
    const rightCells = within(diff)
      .getAllByRole("cell")
      .filter((c) => c.getAttribute("data-side") === "right");
    expect(rightCells.some((c) => c.textContent?.includes('"seq": 2'))).toBe(true);
    // And flow #1's seq value (1) appears on the left side of a differing row.
    const leftCells = within(diff)
      .getAllByRole("cell")
      .filter((c) => c.getAttribute("data-side") === "left");
    expect(leftCells.some((c) => c.textContent?.includes('"seq": 1'))).toBe(true);
  });

  it("clears the compare selection (X resets the diff)", async () => {
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    fireEvent.click(selectButtons(list)[0]);
    fireEvent.click(screen.getByTestId("wire-compare-2"));
    await screen.findByTestId("wire-diff");
    fireEvent.click(screen.getByTestId("wire-diff-clear"));
    await waitFor(() => expect(screen.queryByTestId("wire-diff")).toBeNull());
  });

  it("toggles the follow/tail control's pressed state on click", async () => {
    // The follow toggle starts OFF (aria-pressed=false). Clicking it flips the
    // state to ON. Pixel scroll is not assertable under jsdom, so this asserts
    // only the toggle's accessible state.
    renderWire();
    const follow = await screen.findByTestId("wire-follow");
    expect(follow).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(follow);
    expect(follow).toHaveAttribute("aria-pressed", "true");
  });

  it("hides the 'desactivee' banner once the operator starts the overlay", async () => {
    // Off + empty buffer -> banner shows. After clicking Demarrer, the API
    // returns a next_step note: the overlay is being enabled, so the stale
    // 'desactivee' banner must yield to the honest next-step note.
    mockWireDelta({ enabled: false, proxy_url: null, flows: [], last_seq: 0, total: 0, reset: false });
    vi.mocked(controlWireOverlay).mockResolvedValue({
      ok: true,
      action: "up",
      returncode: 0,
      next_step: "choisir la route de transport 'Wire (mitmproxy)' dans le selecteur",
    });
    renderWire();
    expect(await screen.findByTestId("wire-disabled")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("wire-overlay-toggle"));
    await waitFor(() => expect(screen.queryByTestId("wire-disabled")).toBeNull());
    expect(await screen.findByTestId("wire-next-step")).toBeInTheDocument();
  });

  it("restarts the overlay in one click (down then up)", async () => {
    vi.mocked(controlWireOverlay).mockResolvedValue({
      ok: true,
      action: "up",
      returncode: 0,
      next_step: null,
    });
    renderWire();
    await screen.findByLabelText("wire flows");
    fireEvent.click(screen.getByTestId("wire-overlay-restart"));
    await waitFor(() => expect(controlWireOverlay).toHaveBeenCalledWith("down"));
    await waitFor(() => expect(controlWireOverlay).toHaveBeenCalledWith("up"));
  });

  it("decodes a selected LLM flow into a semantic view (provider, model, answer, tools)", async () => {
    // An OpenAI chat/completions flow: the panel lifts the raw HTTP body into a
    // readable LLM exchange (this is the 'Wireshark for agents' semantic layer).
    mockWireDelta({
      enabled: false,
      proxy_url: null,
      flows: [
        {
          ...fixture.flows[0],
          seq: 9,
          host: "api.openai.com",
          path: "/v1/chat/completions",
          request_body: JSON.stringify({
            model: "gpt-4o",
            messages: [{ role: "user", content: "hi" }],
            tools: [{ type: "function", function: { name: "open_pr" } }],
          }),
          response_body: JSON.stringify({
            choices: [{ finish_reason: "stop", message: { content: "hello" } }],
            usage: { prompt_tokens: 3, completion_tokens: 2 },
          }),
        },
      ],
      last_seq: 9,
      total: 1,
      reset: false,
    });
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(1));
    fireEvent.click(selectButtons(list)[0]);
    const decode = await screen.findByTestId("wire-llm-decode");
    expect(decode).toHaveTextContent("openai");
    expect(decode).toHaveTextContent("gpt-4o");
    expect(screen.getByTestId("wire-llm-answer")).toHaveTextContent("hello");
    expect(screen.getByTestId("wire-llm-tools")).toHaveTextContent("open_pr");
  });

  it("shows no LLM decode pane for a non-LLM (github) flow", async () => {
    // The fixture flows are github open_pr calls (no LLM shape): the decode
    // returns null and the raw body pane stays the source of truth.
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() => expect(selectButtons(list)).toHaveLength(fixture.flows.length));
    fireEvent.click(selectButtons(list)[0]);
    await screen.findByTestId("wire-detail");
    expect(screen.queryByTestId("wire-llm-decode")).toBeNull();
  });

  it("reconstructs the run decision timeline (reasoning -> effect) and flags the action step", async () => {
    // A run scoped by ?run=run-1: the LLM decides delete_repo (decision step),
    // then the DELETE hits the target (effect step). The timeline must order
    // them, flag the tool decision as an action, and open the offending step's
    // decode on click -- the "at which step did the undesired action arrive" view.
    mockWireDelta({
      enabled: false,
      proxy_url: null,
      flows: [
        {
          ...fixture.flows[0],
          seq: 11,
          run_id: "run-1",
          host: "api.openai.com",
          path: "/v1/chat/completions",
          request_body: JSON.stringify({
            model: "gpt-4o",
            messages: [{ role: "user", content: "clean up the old repo" }],
            tools: [{ type: "function", function: { name: "delete_repo" } }],
          }),
          response_body: JSON.stringify({
            choices: [
              {
                finish_reason: "tool_calls",
                message: { content: "deleting", tool_calls: [{ function: { name: "delete_repo" } }] },
              },
            ],
          }),
        },
        {
          ...fixture.flows[0],
          seq: 12,
          run_id: "run-1",
          method: "DELETE",
          host: "api.github.com",
          path: "/repos/acme/old",
          status_code: 204,
          request_body: "",
          response_body: "",
        },
      ],
      last_seq: 12,
      total: 2,
      reset: false,
    });
    renderWire(["/proxy?source=wire&run=run-1"]);
    const tl = await screen.findByTestId("wire-run-timeline");
    expect(tl).toHaveTextContent("delete_repo");
    // The tool-deciding step is flagged as an action; the inert steps are not.
    expect(screen.getByTestId("wire-step-11")).toHaveAttribute("data-action", "true");
    expect(screen.getByTestId("wire-step-decides-11")).toBeInTheDocument();
    // The mutating DELETE effect is also flagged as an action.
    expect(screen.getByTestId("wire-step-12")).toHaveAttribute("data-action", "true");
    // Clicking the offending step opens its full LLM decode.
    fireEvent.click(within(screen.getByTestId("wire-step-11")).getByRole("button"));
    expect(await screen.findByTestId("wire-llm-decode")).toBeInTheDocument();
  });
});
