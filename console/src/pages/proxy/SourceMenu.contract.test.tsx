/**
 * Contract tests for the registry-driven source menu.
 *
 * Renders the real SOURCE_DESCRIPTORS registry so the menu stays in lockstep
 * with what the orchestrator renders: one entry added to the registry is one
 * entry that must appear here.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SourceId, SourceStatus } from "./proxyMenu";
import SourceMenu from "./SourceMenu";
import { SOURCE_DESCRIPTORS } from "./sources";

function renderMenu(
  active: SourceId = "app",
  statusById: Partial<Record<SourceId, SourceStatus>> = {},
): { onSelect: ReturnType<typeof vi.fn> } {
  const onSelect = vi.fn();
  render(
    <SourceMenu
      sources={SOURCE_DESCRIPTORS}
      active={active}
      onSelect={onSelect}
      statusById={statusById}
    />,
  );
  return { onSelect };
}

describe("SourceMenu", () => {
  it("renders one toggle per registered source", () => {
    renderMenu();
    const group = screen.getByRole("group", { name: "source" });
    expect(within(group).getAllByRole("button")).toHaveLength(SOURCE_DESCRIPTORS.length);
  });

  it("marks the active source pressed and the others not", () => {
    renderMenu("wire");
    const wire = screen.getByRole("button", { name: /mitmproxy/ });
    expect(wire).toHaveAttribute("aria-pressed", "true");
    const app = screen.getByRole("button", { name: /traces app/ });
    expect(app).toHaveAttribute("aria-pressed", "false");
  });

  it("calls onSelect with the clicked source id", () => {
    const { onSelect } = renderMenu("app");
    fireEvent.click(screen.getByRole("button", { name: /reconciliation/ }));
    expect(onSelect).toHaveBeenCalledWith("reconcile");
  });

  it("shows a live count badge for a reported healthy status", () => {
    renderMenu("app", { app: { count: 4, failed: 0 } });
    const app = screen.getByRole("button", { name: /traces app/ });
    const badge = within(app).getByText("4");
    expect(badge).toHaveAttribute("data-outcome", "ok");
  });

  it("flags a failing status badge and an off feature", () => {
    renderMenu("reconcile", {
      reconcile: { count: 2, failed: 2 },
      wire: { count: 0, disabled: true },
    });
    expect(within(screen.getByRole("button", { name: /reconciliation/ })).getByText("2 / 2 KO")).toHaveAttribute(
      "data-outcome",
      "fail",
    );
    expect(within(screen.getByRole("button", { name: /mitmproxy/ })).getByText("off")).toHaveAttribute(
      "data-outcome",
      "off",
    );
  });

  it("shows no badge when a source has reported nothing", () => {
    renderMenu("app", {});
    const app = screen.getByRole("button", { name: /traces app/ });
    expect(app.querySelector(".proxy-source-badge")).toBeNull();
  });
});
