/**
 * Mermaid help component (render-and-assert).
 *
 * In jsdom mermaid cannot draw an SVG, so the component must keep its legible
 * <pre> source fallback and never crash -- exactly the behaviour an operator
 * gets before the async render resolves. We assert the fallback + the title.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Mermaid from "./Mermaid";

describe("Mermaid", () => {
  it("renders the title and the legible source fallback", () => {
    render(<Mermaid chart={"flowchart TD\n  A-->B"} title="Ma boucle" />);
    expect(screen.getByTestId("help-mermaid")).toBeInTheDocument();
    expect(screen.getByText("Ma boucle")).toBeInTheDocument();
    // The raw chart source is always present (legibility-first / test-safe).
    expect(screen.getByTestId("help-mermaid-source")).toHaveTextContent("flowchart TD");
  });

  it("does not crash without a title", () => {
    render(<Mermaid chart={"flowchart LR\n  X-->Y"} />);
    expect(screen.getByTestId("help-mermaid")).toBeInTheDocument();
  });
});
