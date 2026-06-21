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
    render(<WirePanel />);
    const list = await screen.findByLabelText("wire flows");
    // The fixture has two flows; both lines show up, newest-first ordering kept.
    expect(within(list).getAllByRole("button")).toHaveLength(fixture.flows.length);
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
    render(<WirePanel />);
    expect(await screen.findByTestId("wire-disabled")).toBeInTheDocument();
  });

  it("hides the how-to-enable banner when flows arrived despite the overlay being off", async () => {
    // Flows can reach the buffer via the transport-route registry even when
    // INSPECT_IA_AGENTS_WIRE_PROXY is unset (enabled=false). The captured fixture is
    // exactly that case: enabled=false WITH real flows. The how-to-enable
    // banner must yield to the actual data, not sit on top of it.
    render(<WirePanel />);
    const list = await screen.findByLabelText("wire flows");
    expect(within(list).getAllByRole("button")).toHaveLength(fixture.flows.length);
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
    render(<WirePanel />);
    expect(await screen.findByTestId("wire-disabled")).toBeInTheDocument();
  });

  it("shows the proxy URL when the overlay is enabled", async () => {
    vi.mocked(getWireFlows).mockResolvedValue({
      ...fixture,
      enabled: true,
      proxy_url: "http://127.0.0.1:8083",
    });
    render(<WirePanel />);
    const url = await screen.findByTestId("wire-proxy-url");
    expect(url).toHaveTextContent("http://127.0.0.1:8083");
    expect(screen.queryByTestId("wire-disabled")).not.toBeInTheDocument();
  });

  it("inspects a selected flow's request and response bodies", async () => {
    render(<WirePanel />);
    const list = await screen.findByLabelText("wire flows");
    fireEvent.click(within(list).getAllByRole("button")[0]);
    const detail = await screen.findByTestId("wire-detail");
    // The first fixture flow is the open_pr request -> 201 success body.
    expect(detail).toHaveTextContent("open_pr");
    expect(detail).toHaveTextContent('"number":42');
    expect(detail).toHaveTextContent("201");
  });

  it("copies a curl command for the selected flow", async () => {
    render(<WirePanel />);
    const list = await screen.findByLabelText("wire flows");
    fireEvent.click(within(list).getAllByRole("button")[0]);
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
    render(<WirePanel />);
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
    render(<WirePanel />);
    await screen.findByLabelText("wire flows");
    fireEvent.click(screen.getByText("Vider le tampon"));
    await waitFor(() => expect(clearWireFlows).toHaveBeenCalledTimes(1));
  });

  it("narrows the flow list when a text filter matches only some flows", async () => {
    // The fixture has two flows on the same host/method/path; only flow #1's
    // request_body carries the "open_pr" token, so it is the only match.
    render(<WirePanel />);
    const list = await screen.findByLabelText("wire flows");
    expect(within(list).getAllByRole("button")).toHaveLength(fixture.flows.length);

    const text = screen.getByTestId("wire-filter-text");
    fireEvent.change(text, { target: { value: "open_pr" } });

    await waitFor(() =>
      expect(within(list).getAllByRole("button").length).toBeLessThan(fixture.flows.length),
    );
    expect(within(list).getAllByRole("button")).toHaveLength(1);
  });

  it("exports the shown flows as HAR", async () => {
    render(<WirePanel />);
    await screen.findByLabelText("wire flows");
    fireEvent.click(screen.getByTestId("wire-export-har"));
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});
