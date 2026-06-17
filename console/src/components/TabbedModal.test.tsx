/**
 * TabbedModal regression tests.
 *
 * The key invariant: changing the TAB SET while the modal stays open (e.g. a
 * consumer morphing a one-tab loading placeholder into the loaded N-tab set)
 * must NOT reset the user's active tab. A reset-on-length-change effect used to
 * race the user's click and snap the selection back to tab 0 (observed as a
 * flaky "clicking Actions does not switch" failure downstream).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TabbedModal from "./TabbedModal";
import type { Tab } from "./TabbedModal";

function tabs(labels: string[]): Tab[] {
  return labels.map((label) => ({
    key: label,
    label,
    content: <p data-testid={`panel-${label}`}>{label} content</p>,
  }));
}

describe("TabbedModal", () => {
  it("keeps the user's selected tab when the tab SET grows (loading -> loaded)", () => {
    const { rerender } = render(
      <TabbedModal open title="t" tabs={tabs(["Loading"])} onClose={vi.fn()} />,
    );

    // Loaded: the consumer swaps the single placeholder tab for the real set.
    rerender(
      <TabbedModal open title="t" tabs={tabs(["A", "B", "C"])} onClose={vi.fn()} />,
    );

    // The user selects B.
    fireEvent.click(screen.getByRole("tab", { name: "B" }));
    expect(screen.getByRole("tab", { name: "B" })).toHaveAttribute("aria-selected", "true");

    // A later re-render that grows the tab set must NOT reset back to A.
    rerender(
      <TabbedModal open title="t" tabs={tabs(["A", "B", "C", "D"])} onClose={vi.fn()} />,
    );
    expect(screen.getByRole("tab", { name: "B" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("panel-B")).toBeInTheDocument();
  });

  it("resets to the first tab when the modal is re-opened", () => {
    const { rerender } = render(
      <TabbedModal open title="t" tabs={tabs(["A", "B", "C"])} onClose={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "C" }));
    expect(screen.getByRole("tab", { name: "C" })).toHaveAttribute("aria-selected", "true");

    // Close then re-open: a fresh open starts on the first tab.
    rerender(<TabbedModal open={false} title="t" tabs={tabs(["A", "B", "C"])} onClose={vi.fn()} />);
    rerender(<TabbedModal open title="t" tabs={tabs(["A", "B", "C"])} onClose={vi.fn()} />);
    expect(screen.getByRole("tab", { name: "A" })).toHaveAttribute("aria-selected", "true");
  });

  it("clamps the active index when the tab set shrinks below it", () => {
    const { rerender } = render(
      <TabbedModal open title="t" tabs={tabs(["A", "B", "C"])} onClose={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "C" }));
    // Shrink to two tabs: the previously-active index 2 is out of range and is
    // clamped to the last tab, never crashing.
    rerender(<TabbedModal open title="t" tabs={tabs(["A", "B"])} onClose={vi.fn()} />);
    expect(screen.getByRole("tab", { name: "B" })).toHaveAttribute("aria-selected", "true");
  });
});
