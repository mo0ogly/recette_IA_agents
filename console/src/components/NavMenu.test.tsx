/**
 * Tests for the grouped dropdown navigation.
 *
 * Pure navigation component: it issues no API call of its own, but it renders
 * ProxyNavBadge (which does), so the client is mocked to keep the header inert.
 * A MemoryRouter supplies the NavLink / useLocation context.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, getProxyDebugStatus: vi.fn().mockRejectedValue(new Error("inert")) };
});

import NavMenu from "./NavMenu";

function renderNav(initialPath = "/dashboard"): void {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <NavMenu />
    </MemoryRouter>,
  );
}

describe("NavMenu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the standalone home link and the six group buttons", () => {
    renderNav();
    expect(screen.getByRole("link", { name: "Tableau de bord" })).toBeInTheDocument();
    for (const group of ["Discovery", "Recette", "Agents", "Runs & flux", "Gouvernance", "Observabilite"]) {
      expect(screen.getByRole("button", { name: new RegExp(group) })).toBeInTheDocument();
    }
  });

  it("keeps group items hidden until the group button is clicked", () => {
    renderNav();
    expect(screen.queryByRole("link", { name: "Reperage" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Discovery/ }));
    expect(screen.getByRole("link", { name: "Reperage" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Probe" })).toBeInTheDocument();
  });

  it("opening one group closes the previously open one", () => {
    renderNav();
    fireEvent.click(screen.getByRole("button", { name: /Discovery/ }));
    expect(screen.getByRole("link", { name: "Probe" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Recette/ }));
    expect(screen.queryByRole("link", { name: "Probe" })).toBeNull();
    expect(screen.getByRole("link", { name: "Red-team" })).toBeInTheDocument();
  });

  it("marks the group that owns the active route", () => {
    renderNav("/runs");
    const runsButton = screen.getByRole("button", { name: /Runs & flux/ });
    expect(runsButton.className).toContain("nav-group-button-active");
  });
});
