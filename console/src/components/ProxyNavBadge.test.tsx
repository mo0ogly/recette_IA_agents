/**
 * Tests for the proxy debug nav badge.
 *
 * The api client is mocked so the badge renders against the exact status shape
 * the backend returns, and a fetch failure hides the badge (no header crash).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, getProxyDebugStatus: vi.fn() };
});

import { getProxyDebugStatus } from "../api/client";
import ProxyNavBadge from "./ProxyNavBadge";

describe("ProxyNavBadge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows ON when debug tracing is enabled", async () => {
    vi.mocked(getProxyDebugStatus).mockResolvedValue({ debug_enabled: true, trace_count: 3 });
    render(<ProxyNavBadge />);
    const badge = await screen.findByText("debug ON");
    expect(badge).toHaveAttribute("data-enabled", "true");
  });

  it("shows OFF when debug tracing is disabled", async () => {
    vi.mocked(getProxyDebugStatus).mockResolvedValue({ debug_enabled: false, trace_count: 0 });
    render(<ProxyNavBadge />);
    const badge = await screen.findByText("debug OFF");
    expect(badge).toHaveAttribute("data-enabled", "false");
  });

  it("renders nothing on a fetch failure (no header crash)", async () => {
    vi.mocked(getProxyDebugStatus).mockRejectedValue(new Error("down"));
    const { container } = render(<ProxyNavBadge />);
    await waitFor(() => expect(getProxyDebugStatus).toHaveBeenCalled());
    expect(container.querySelector(".proxy-nav-badge")).toBeNull();
  });
});
