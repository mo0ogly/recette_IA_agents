/**
 * HelpModal tests -- accessibility contract of the per-page help dialog:
 * closed renders nothing; open renders role=dialog labelled by its title with
 * focus on the close button; Escape and backdrop click close it, a click
 * inside the dialog does not.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import HelpModal from "./HelpModal";

function renderModal(open: boolean): { onClose: ReturnType<typeof vi.fn> } {
  const onClose = vi.fn();
  render(
    <HelpModal open={open} title="Aide -- Test" onClose={onClose}>
      <p>contenu d'aide</p>
    </HelpModal>,
  );
  return { onClose };
}

describe("HelpModal", () => {
  it("renders nothing when closed", () => {
    renderModal(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders an accessible dialog with the title and focuses the close button", () => {
    renderModal(true);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("heading", { name: "Aide -- Test" })).toBeInTheDocument();
    expect(screen.getByText("contenu d'aide")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fermer l'aide" })).toHaveFocus();
  });

  it("closes on Escape", () => {
    const { onClose } = renderModal(true);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on backdrop click but not on a click inside the dialog", () => {
    const { onClose } = renderModal(true);
    fireEvent.click(screen.getByText("contenu d'aide"));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("help-modal-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes via the close button", () => {
    const { onClose } = renderModal(true);
    fireEvent.click(screen.getByRole("button", { name: "Fermer l'aide" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
