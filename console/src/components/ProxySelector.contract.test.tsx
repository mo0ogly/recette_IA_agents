/**
 * R16 contract tests for the shared proxy-route selector.
 *
 * The fixture in __fixtures__/proxy-route.fixture.json was captured from the
 * real backend (GET /proxy/route via TestClient), not invented. The api client
 * is mocked so the component renders against the exact payload shape.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ProxyRouteState } from "../types/platform";
import routeFixture from "./__fixtures__/proxy-route.fixture.json";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    getProxyRoute: vi.fn(),
    setProxyRoute: vi.fn(),
  };
});

import { getProxyRoute, setProxyRoute } from "../api/client";
import ProxySelector from "./ProxySelector";

const fixture = routeFixture as ProxyRouteState;

describe("ProxySelector (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getProxyRoute).mockResolvedValue(fixture);
    vi.mocked(setProxyRoute).mockResolvedValue({ active: "wire", proxy_url: "http://127.0.0.1:8083" });
  });

  it("renders one button per target and marks the active one", async () => {
    render(<ProxySelector />);
    const group = await screen.findByTestId("proxy-selector");
    const buttons = within(group).getAllByRole("button");
    expect(buttons).toHaveLength(fixture.targets.length);
    const direct = buttons.find((b) => b.textContent === "Direct (sans proxy)");
    expect(direct).toHaveAttribute("data-active", "true");
  });

  it("switches the active route on click", async () => {
    render(<ProxySelector />);
    const group = await screen.findByTestId("proxy-selector");
    const wireBtn = within(group)
      .getAllByRole("button")
      .find((b) => b.textContent === "Wire (mitmproxy)");
    fireEvent.click(wireBtn!);
    await waitFor(() => expect(setProxyRoute).toHaveBeenCalledWith("wire"));
    await waitFor(() => expect(wireBtn).toHaveAttribute("data-active", "true"));
  });
});
