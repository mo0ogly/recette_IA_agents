/**
 * InsightsJournal: empty state, reverse-chrono render, and the text filter.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AssistInsight } from "../../types/assist";

import InsightsJournal from "./InsightsJournal";

function insight(id: string, label: string, answer: string): AssistInsight {
  return { id, topic: `${label}.t`, label, answer, model: "m", created_at: "2026-07-07T08:00:00Z" };
}

describe("InsightsJournal", () => {
  it("shows the empty state with no insights", () => {
    render(<InsightsJournal insights={[]} />);
    expect(screen.getByTestId("assist-journal-empty")).toBeInTheDocument();
  });

  it("renders newest first", () => {
    render(
      <InsightsJournal
        insights={[insight("i-1", "Agents", "aaa"), insight("i-2", "Verdicts", "bbb")]}
      />,
    );
    const labels = screen.getAllByText(/Agents|Verdicts/).map((n) => n.textContent);
    expect(labels[0]).toBe("Verdicts");
  });

  it("filters by label, topic or answer", () => {
    render(
      <InsightsJournal
        insights={[
          insight("i-1", "Agents", "un texte sur les scopes"),
          insight("i-2", "Verdicts", "un texte sur les checks"),
        ]}
      />,
    );
    const filter = screen.getByLabelText("Filtrer le journal");
    fireEvent.change(filter, { target: { value: "scopes" } });
    expect(screen.getByText("Agents")).toBeInTheDocument();
    expect(screen.queryByText("Verdicts")).not.toBeInTheDocument();
    fireEvent.change(filter, { target: { value: "zzz" } });
    expect(screen.getByTestId("assist-journal-nomatch")).toBeInTheDocument();
  });
});
