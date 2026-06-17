import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import PageHelp from "./PageHelp";
import { HELP_TOPICS } from "./helpTopics";

describe("PageHelp", () => {
  it("renders a trigger and no dialog until opened", () => {
    render(<PageHelp topic="agents" />);
    expect(screen.getByRole("button", { name: /aide/i })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens the topic dialog with its title and summary", () => {
    render(<PageHelp topic="approvals" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeTruthy();
    expect(screen.getByText(HELP_TOPICS.approvals.title)).toBeTruthy();
    expect(screen.getByText(HELP_TOPICS.approvals.summary)).toBeTruthy();
  });

  it("closes on the close button", () => {
    render(<PageHelp topic="audit" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /fermer l'aide/i }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders the redteam topic with its MAF and git detail blocks", () => {
    render(<PageHelp topic="redteam" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    expect(screen.getByText(HELP_TOPICS.redteam.title)).toBeTruthy();
    // "Capacites declarees" / "hors perimetre" now appear in BOTH the MAF and the
    // git (Lane B) detail sections -- assert each is present at least once.
    expect(screen.getAllByText(/Capacites declarees/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/hors perimetre/).length).toBeGreaterThan(0);
    // The git (Lane B) section is present and goal-driven.
    expect(screen.getByText(/Detail d'un agent Git \(Lane B\)/)).toBeTruthy();
    // The redteam topic embeds the two mermaid diagrams (engine + loop).
    expect(screen.getAllByTestId("help-mermaid").length).toBeGreaterThanOrEqual(2);
  });

  it("renders the probe and observability topics (the discovery + traces pages)", () => {
    const { unmount } = render(<PageHelp topic="probe" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    expect(screen.getByText(HELP_TOPICS.probe.title)).toBeTruthy();
    expect(screen.getByText(HELP_TOPICS.probe.summary)).toBeTruthy();
    // The discovery probe term replaced the legacy "RailNode" wording.
    expect(screen.getAllByText(/sonde discovery/).length).toBeGreaterThan(0);
    unmount();

    render(<PageHelp topic="observability" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    expect(screen.getByText(HELP_TOPICS.observability.title)).toBeTruthy();
    expect(screen.getByText(HELP_TOPICS.observability.summary)).toBeTruthy();
  });

  it("closes on backdrop click", () => {
    render(<PageHelp topic="catalog" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    fireEvent.click(screen.getByTestId("help-modal-backdrop"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("documents private-DNS containment in the servers topic with its diagram", () => {
    render(<PageHelp topic="servers" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    expect(screen.getByText(HELP_TOPICS.servers.title)).toBeTruthy();
    // The new FQDN/alias/containment section and its mermaid diagram are present.
    expect(screen.getByText(/Noms prives : FQDN, alias et containment/)).toBeTruthy();
    expect(screen.getAllByText(/resolution_denied/).length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("help-mermaid").length).toBeGreaterThanOrEqual(1);
  });
});
