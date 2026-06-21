/**
 * R16 contract tests for the wire-overlay panel.
 *
 * The fixture in __fixtures__/wire.fixture.json was captured from the real
 * backend (recette.api driven through TestClient: POST /proxy/wire then GET
 * /proxy/wire), not invented. The api client is mocked so the panel renders
 * against the exact payload shape the backend returns. Covers both overlay
 * states (disabled -> hint banner; enabled -> proxy URL shown) and the
 * select-and-inspect flow.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WireFlowResponse } from "../../types/platform";
import wireFixture from "./__fixtures__/wire.fixture.json";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    getWireFlows: vi.fn(),
    clearWireFlows: vi.fn(),
    controlWireOverlay: vi.fn(),
  };
});

import { clearWireFlows, controlWireOverlay, getWireFlows } from "../../api/client";
import WirePanel from "./WirePanel";

const fixture = wireFixture as WireFlowResponse;

/**
 * WirePanel now reads its filter clauses from the URL query string
 * (useSearchParams), so every render needs a router. `entries` lets a test
 * open the panel pre-filtered (deep-link) on first render.
 */
function renderWire(entries: string[] = ["/proxy"]): void {
  render(
    <MemoryRouter initialEntries={entries}>
      <WirePanel />
    </MemoryRouter>,
  );
}

/**
 * The per-flow SELECT buttons (one per flow). Each list row now carries two
 * buttons -- the select button (`proxy-list-item`) and a "comparer" button --
 * so the flow count is the count of select buttons, queried by class rather
 * than the raw button role.
 */
function selectButtons(list: HTMLElement): HTMLElement[] {
  return within(list)
    .getAllByRole("button")
    .filter((b) => b.classList.contains("proxy-list-item"));
}

describe("WirePanel (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getWireFlows).mockResolvedValue(fixture);
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
    // The fixture has two flows; both lines show up, newest-first ordering kept.
    expect(selectButtons(list)).toHaveLength(fixture.flows.length);
    expect(screen.getByText(/2 flux, 1 echec/)).toBeInTheDocument();
  });

  it("shows the disabled banner when the overlay is off and no flows arrived", async () => {
    // enabled=false (no INSPECT_IA_AGENTS_WIRE_PROXY in the capture env) AND an
    // empty buffer: the panel must explain how to enable it, not show a bare
    // empty list as a steady state.
    vi.mocked(getWireFlows).mockResolvedValue({
      enabled: false,
      proxy_url: null,
      flows: [],
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
    const list = await screen.findByLabelText("wire flows");
    expect(selectButtons(list)).toHaveLength(fixture.flows.length);
    expect(screen.queryByText(/wire up/)).toBeNull();
    expect(screen.queryByText(/INSPECT_IA_AGENTS_WIRE_PROXY/)).toBeNull();
    expect(screen.queryByTestId("wire-disabled")).toBeNull();
  });

  it("shows the how-to-enable banner when the overlay is off and there are no flows", async () => {
    vi.mocked(getWireFlows).mockResolvedValue({
      enabled: false,
      proxy_url: null,
      flows: [],
    });
    renderWire();
    expect(await screen.findByTestId("wire-disabled")).toBeInTheDocument();
  });

  it("shows the proxy URL when the overlay is enabled", async () => {
    vi.mocked(getWireFlows).mockResolvedValue({
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
      next_step:
        "set INSPECT_IA_AGENTS_WIRE_PROXY + trust the CA, then ./recette.sh api restart",
    });
    renderWire();
    const toggle = await screen.findByTestId("wire-overlay-toggle");
    fireEvent.click(toggle);
    await waitFor(() => expect(controlWireOverlay).toHaveBeenCalledWith("up"));
    expect(
      await screen.findByText(
        /set INSPECT_IA_AGENTS_WIRE_PROXY \+ trust the CA, then \.\/recette\.sh api restart/,
      ),
    ).toBeInTheDocument();
  });

  it("clears the buffer on demand", async () => {
    renderWire();
    await screen.findByLabelText("wire flows");
    fireEvent.click(screen.getByText("Vider le tampon"));
    await waitFor(() => expect(clearWireFlows).toHaveBeenCalledTimes(1));
  });

  it("narrows the flow list when a text filter matches only some flows", async () => {
    // The fixture has two flows on the same host/method/path; only flow #1's
    // request_body carries the "open_pr" token, so it is the only match.
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    expect(selectButtons(list)).toHaveLength(fixture.flows.length);

    const text = screen.getByTestId("wire-filter-text");
    fireEvent.change(text, { target: { value: "open_pr" } });

    await waitFor(() =>
      expect(selectButtons(list).length).toBeLessThan(fixture.flows.length),
    );
    expect(selectButtons(list)).toHaveLength(1);
  });

  it("flags a body clamped by the backend (truncation marker) and not a normal body", async () => {
    // The detector keys off the literal marker appended by wire.py _clamp_body,
    // not a numeric length, so a body ending in the marker is flagged truncated
    // while a normal short body is not (zero false-positive).
    vi.mocked(getWireFlows).mockResolvedValue({
      enabled: false,
      proxy_url: null,
      flows: [
        {
          ...fixture.flows[0],
          seq: 7,
          request_body: '{"big":"x"}...[truncated]',
        },
      ],
    });
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    fireEvent.click(selectButtons(list)[0]);
    await screen.findByTestId("wire-detail");
    expect(screen.getByTestId("wire-req-truncated")).toBeInTheDocument();
  });

  it("does not flag a normal (non-marker) body as truncated", async () => {
    // The first fixture flow carries a short, un-clamped request_body, so no
    // truncation marker -> no truncated badge.
    renderWire();
    const list = await screen.findByLabelText("wire flows");
    fireEvent.click(selectButtons(list)[0]);
    await screen.findByTestId("wire-detail");
    expect(screen.queryByTestId("wire-req-truncated")).toBeNull();
    expect(screen.queryByTestId("wire-resp-truncated")).toBeNull();
  });

  it("shows the per-exchange latency in the detail pane when duration_ms is set", async () => {
    // duration_ms is OPS metadata on the wire view only (never a judge input,
    // I4). When present, the detail pane surfaces it as a latency line.
    vi.mocked(getWireFlows).mockResolvedValue({
      enabled: false,
      proxy_url: null,
      flows: [{ ...fixture.flows[0], seq: 5, duration_ms: 42 }],
    });
    renderWire();
    const list = await screen.findByLabelText("wire flows");
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
    // the list to that single flow WITHOUT any typing.
    renderWire(["/proxy?source=wire&q=open_pr"]);
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() =>
      expect(selectButtons(list)).toHaveLength(1),
    );
    // The free-text input reflects the URL value (controlled by the query).
    expect(screen.getByTestId("wire-filter-text")).toHaveValue("open_pr");
  });

  it("opens pre-filtered by host from ?host= on first render (deep-link)", async () => {
    // Both fixture flows are on host 127.0.0.1, so ?host=127.0.0.1 keeps both
    // and proves the host clause is driven by the URL. A non-matching host
    // empties the list.
    renderWire(["/proxy?source=wire&host=127.0.0.1"]);
    const list = await screen.findByLabelText("wire flows");
    await waitFor(() =>
      expect(selectButtons(list)).toHaveLength(fixture.flows.length),
    );
    expect(screen.getByDisplayValue("127.0.0.1")).toBeInTheDocument();
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
});
