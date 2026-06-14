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
  };
});

import { clearWireFlows, getWireFlows } from "../../api/client";
import WirePanel from "./WirePanel";

const fixture = wireFixture as WireFlowResponse;

describe("WirePanel (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getWireFlows).mockResolvedValue(fixture);
    vi.mocked(clearWireFlows).mockResolvedValue({ cleared: true });
  });

  it("renders the captured flows without crashing", async () => {
    render(<WirePanel />);
    const list = await screen.findByLabelText("wire flows");
    // The fixture has two flows; both lines show up, newest-first ordering kept.
    expect(within(list).getAllByRole("button")).toHaveLength(fixture.flows.length);
    expect(screen.getByText(/2 flux, 1 echec/)).toBeInTheDocument();
  });

  it("shows the disabled banner when the overlay is off", async () => {
    // The captured fixture has enabled=false (no INSPECT_IA_AGENTS_WIRE_PROXY in the
    // capture env): the panel must explain how to enable it, not show a bare list.
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

  it("clears the buffer on demand", async () => {
    render(<WirePanel />);
    await screen.findByLabelText("wire flows");
    fireEvent.click(screen.getByText("Vider le tampon"));
    await waitFor(() => expect(clearWireFlows).toHaveBeenCalledTimes(1));
  });
});
