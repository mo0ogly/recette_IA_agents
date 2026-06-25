import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RunTreeComponent from "./RunTree";
import type { RunTree } from "../../api/client";
import fixture from "./__fixtures__/runs-tree.fixture.json";

describe("RunTree", () => {
  it("renders category label, group eurodate and a run id", () => {
    const onSelect = vi.fn();
    render(
      <RunTreeComponent
        data={fixture as RunTree}
        selectedId={null}
        onSelect={onSelect}
      />,
    );

    // Category level
    expect(screen.getByTestId("run-category-skynet")).toBeInTheDocument();
    // Group level shows eurodate
    expect(screen.getByTestId("run-group-megacamp-demo")).toBeInTheDocument();
    expect(screen.getByTestId("run-group-megacamp-demo")).toHaveTextContent(
      "2026-06-25T14-30-00",
    );
    // Run level shows id
    expect(screen.getByTestId("run-node-agents-fleet")).toBeInTheDocument();
  });

  it("calls onSelect with the run id when a run is clicked", () => {
    const onSelect = vi.fn();
    render(
      <RunTreeComponent
        data={fixture as RunTree}
        selectedId={null}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByTestId("run-node-agents-fleet").querySelector("button")!);
    expect(onSelect).toHaveBeenCalledWith("agents-fleet");
  });

  it("collapses and expands a category on click", () => {
    const onSelect = vi.fn();
    render(
      <RunTreeComponent
        data={fixture as RunTree}
        selectedId={null}
        onSelect={onSelect}
      />,
    );

    const catBtn = screen.getByTestId("run-category-skynet").querySelector("button")!;
    // Initially expanded: group is visible
    expect(screen.getByTestId("run-group-megacamp-demo")).toBeInTheDocument();
    // Collapse
    fireEvent.click(catBtn);
    expect(screen.queryByTestId("run-group-megacamp-demo")).not.toBeInTheDocument();
    // Expand again
    fireEvent.click(catBtn);
    expect(screen.getByTestId("run-group-megacamp-demo")).toBeInTheDocument();
  });

  it("marks the selected run with aria-current", () => {
    const onSelect = vi.fn();
    render(
      <RunTreeComponent
        data={fixture as RunTree}
        selectedId="agents-fleet"
        onSelect={onSelect}
      />,
    );

    const btn = screen.getByTestId("run-node-agents-fleet").querySelector("button")!;
    expect(btn).toHaveAttribute("aria-current", "true");
  });
});
