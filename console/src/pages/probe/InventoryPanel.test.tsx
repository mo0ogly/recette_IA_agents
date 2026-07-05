/**
 * R16 contract gate for the InventoryPanel: render against a REAL captured
 * payload (__fixtures__/inventory-panel.fixture.json, the bytes of a live
 * GET /probe/inventory .inventory body) and assert the panel renders correctly.
 *
 * The fixture carries all THREE passport (manifest) states so each badge is
 * exercised (present | absent | invalid) AND all FOUR attestation (signed) states
 * on the orthogonal axis (trusted | untrusted | unsigned | malformed), with the
 * untrusted agent carrying typed reasons (bad_signature + scope_overreach{extra}
 * + malformed_field{field}) so the discriminated-union reason rendering is
 * covered. It also carries a PassportAbsent violation and a real undeclared
 * communication edge, so the violations list and the undeclared-edge flag are
 * asserted against real data -- not an invented payload.
 *
 * Consumer contract asserted here: the INVALID agent shows the "invalid" badge
 * even though it carries NO violation (the badge keys off passport_status, not
 * a non-empty violations list); and the attestation axis is INDEPENDENT of the
 * manifest axis (a present manifest can be unsigned; a shadow can be untrusted).
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
    // Two agents carry a present manifest (acme-dependency-pr-bot + the unsigned
    // acme-release-notifier), so select all for the present badge.
    expect(screen.getAllByTestId("inv-badge-present")[0].textContent).toBe("present");
    expect(screen.getByTestId("inv-badge-absent").textContent).toBe("absent");
    expect(screen.getByTestId("inv-badge-invalid").textContent).toBe("invalid");
  });

  it("shows the attestation badge for EACH of trusted / untrusted / unsigned / malformed", () => {
    // R16 discriminated-union coverage of the signed-attestation axis: every one
    // of the four Attestation kinds renders its own badge, keyed off kind alone.
    render(<InventoryPanel inventory={REAL} />);
    expect(screen.getByTestId("inv-attest-trusted").textContent).toContain("trusted");
    expect(screen.getByTestId("inv-attest-untrusted").textContent).toContain(
      "untrusted",
    );
    expect(screen.getByTestId("inv-attest-unsigned").textContent).toContain("unsigned");
    expect(screen.getByTestId("inv-attest-malformed").textContent).toContain(
      "malformed",
    );
  });

  it("renders the untrusted reasons, including scope_overreach extra and malformed_field field", () => {
    // The untrusted agent carries three typed reasons; the badge must surface
    // WHY -- the bare reason kinds AND the distinguishing fields (extra scope,
    // offending field) -- so an operator sees the cause.
    render(<InventoryPanel inventory={REAL} />);
    const badge = screen.getByTestId("inv-attest-untrusted");
    expect(badge.textContent).toContain("bad_signature");
    expect(badge.textContent).toContain("scope_overreach");
    expect(badge.textContent).toContain("manage_webhook");
    expect(badge.textContent).toContain("push");
    expect(badge.textContent).toContain("malformed_field");
    expect(badge.textContent).toContain("exp");
  });

  it("renders the malformed attestation parse message", () => {
    render(<InventoryPanel inventory={REAL} />);
    expect(screen.getByTestId("inv-attest-malformed").textContent).toContain(
      "passport.json",
    );
  });

  it("treats attestation as an axis orthogonal to the manifest passport", () => {
    // A present manifest can be unsigned (acme-release-notifier) while another
    // present manifest is trusted (acme-dependency-pr-bot): the two axes do not
    // imply each other.
    const presentAgents = REAL.agents.filter((a) => a.passport.kind === "present");
    const attestKinds = presentAgents.map((a) => a.attestation.kind).sort();
    expect(attestKinds).toEqual(["trusted", "unsigned"]);
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
