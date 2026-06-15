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

  it("renders the redteam topic with its MAF detail blocks", () => {
    render(<PageHelp topic="redteam" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    expect(screen.getByText(HELP_TOPICS.redteam.title)).toBeTruthy();
    expect(screen.getByText(/Capacites declarees/)).toBeTruthy();
    expect(screen.getByText(/hors perimetre/)).toBeTruthy();
  });

  it("closes on backdrop click", () => {
    render(<PageHelp topic="catalog" />);
    fireEvent.click(screen.getByRole("button", { name: /aide/i }));
    fireEvent.click(screen.getByTestId("help-modal-backdrop"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
