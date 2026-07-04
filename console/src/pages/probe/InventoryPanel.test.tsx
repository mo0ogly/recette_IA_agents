/**
 * R16 contract gate for the InventoryPanel: render against a REAL captured
 * payload (__fixtures__/inventory-panel.fixture.json, the bytes of a live
 * GET /probe/inventory .inventory body) and assert the panel renders correctly.
 *
 * The fixture carries all THREE passport states so each badge is exercised
 * (present | absent | invalid). It also carries a PassportAbsent violation and
 * a real undeclared communication edge, so the violations list and the
 * undeclared-edge flag are asserted against real data -- not an invented payload.
 *
 * Consumer contract asserted here: the INVALID agent shows the "invalid" badge
 * even though it carries NO violation (the badge keys off passport_status, not
 * a non-empty violations list).
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import InventoryPanel from "./InventoryPanel";
import type { AgentInventory } from "../../api/client";
import fixture from "./__fixtures__/inventory-panel.fixture.json";

const REAL = fixture as unknown as AgentInventory;

describe("InventoryPanel (R16)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders without console errors from a real captured payload", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<InventoryPanel inventory={REAL} />);
    expect(screen.getByTestId("inv-panel")).toBeInTheDocument();
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it("renders an agent row", () => {
    render(<InventoryPanel inventory={REAL} />);
    expect(screen.getByTestId("inv-agents-table")).toBeInTheDocument();
    // the present agent id is visible in its row
    expect(screen.getByTestId("inv-agent-row-0")).toHaveTextContent(
      "acme-dependency-pr-bot[bot]",
    );
  });

  it("shows the passport badge for EACH of present / absent / invalid", () => {
    render(<InventoryPanel inventory={REAL} />);
    expect(screen.getByTestId("inv-badge-present").textContent).toBe("present");
    expect(screen.getByTestId("inv-badge-absent").textContent).toBe("absent");
    expect(screen.getByTestId("inv-badge-invalid").textContent).toBe("invalid");
  });

  it("keeps the invalid badge for an invalid passport that has NO violation", () => {
    // Consumer contract: an invalid passport carries not_observed conformity and
    // no violation, yet the badge must read "invalid" (keyed off passport_status).
    const invalidAgent = REAL.agents.find((a) => a.passport.kind === "invalid");
    expect(invalidAgent).toBeDefined();
    expect(invalidAgent?.conformity.kind).toBe("not_observed");
    render(<InventoryPanel inventory={REAL} />);
    expect(screen.getByTestId("inv-badge-invalid")).toBeInTheDocument();
  });

  it("surfaces a violation (PassportAbsent)", () => {
    render(<InventoryPanel inventory={REAL} />);
    expect(screen.getByTestId("inv-violations")).toBeInTheDocument();
    expect(screen.getByTestId("inv-violation-passport_absent")).toBeInTheDocument();
  });

  it("flags an undeclared communication edge", () => {
    render(<InventoryPanel inventory={REAL} />);
    const group = screen.getByTestId("inv-edges-undeclared");
    // the real fixture carries exactly one undeclared edge
    expect(group.textContent).toMatch(/undeclared \(1\)/);
    expect(group.querySelector(".inv-edge-undeclared")).not.toBeNull();
  });

  it("shows via-gateway edges separately from undeclared", () => {
    render(<InventoryPanel inventory={REAL} />);
    expect(screen.getByTestId("inv-edges-gateway")).toBeInTheDocument();
    expect(screen.getByTestId("inv-edges-gateway").textContent).toMatch(
      /via gateway \(1\)/,
    );
  });

  it("returns null when no inventory is provided (offline fail-safe)", () => {
    const { container } = render(<InventoryPanel inventory={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the LIVE SCAN badge when the inventory is a live scan", () => {
    render(<InventoryPanel inventory={REAL} live={true} />);
    expect(screen.getByTestId("inv-live-badge").textContent).toBe("LIVE SCAN");
  });

  it("shows the SAMPLE badge with the fallback reason when not live", () => {
    render(
      <InventoryPanel inventory={REAL} live={false} reason="engine not built" />,
    );
    const badge = screen.getByTestId("inv-live-badge");
    expect(badge.textContent).toBe("SAMPLE");
    expect(badge.getAttribute("title")).toBe("engine not built");
  });
});
