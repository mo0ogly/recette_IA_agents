import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RunViewer from "./RunViewer";
import { getOrchestrationView } from "../../api/client";
import type { RunView } from "../../api/client";
import fixture from "./__fixtures__/runview.fixture.json";
import handoffFixture from "./__fixtures__/runview-handoff.fixture.json";

vi.mock("../../api/client", () => ({
  getOrchestrationView: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("RunViewer", () => {
  it("renders the verdict, dimensions and step timeline from a real payload", async () => {
    vi.mocked(getOrchestrationView).mockResolvedValue(fixture as RunView);
    render(<RunViewer agentId="concurrent-review-capability-overreach" />);

    // verdict + the broken dimension surface.
    expect(await screen.findByTestId("runview-verdict")).toHaveTextContent("incorrect");
    expect(screen.getByTestId("runview-dim-capabilities")).toHaveClass("pill-bad");
    expect(screen.getByTestId("runview-dim-identity")).toHaveClass("pill-ok");
    // one step per executed participant.
    expect(screen.getByTestId("runview-step-0")).toBeInTheDocument();
    // the Mermaid diagram is present.
    expect(screen.getByTestId("runview-mermaid")).toHaveTextContent("flowchart TD");
  });

  it("shows the declared reason of each handoff (team conversation)", async () => {
    vi.mocked(getOrchestrationView).mockResolvedValue(handoffFixture as RunView);
    render(<RunViewer agentId="finance-approval-handoff-correct" />);

    await screen.findByTestId("runview-step-0");
    expect(screen.getByTestId("runview-reason-0")).toHaveTextContent(
      "payment request validated, needs an approved wire execution",
    );
    // Tool steps carry no reason element.
    expect(screen.queryByTestId("runview-reason-3")).toBeNull();
  });

  it("steps the cursor forward through the timeline", async () => {
    vi.mocked(getOrchestrationView).mockResolvedValue(fixture as RunView);
    render(<RunViewer agentId="x" />);
    await screen.findByTestId("runview-cursor");
    expect(screen.getByTestId("runview-cursor")).toHaveTextContent("step 1/");

    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByTestId("runview-cursor")).toHaveTextContent("step 2/");
  });

  it("shows an inline error when the fetch fails", async () => {
    vi.mocked(getOrchestrationView).mockRejectedValue(new Error("boom"));
    render(<RunViewer agentId="x" />);
    await waitFor(() => expect(screen.getByTestId("runview-error")).toHaveTextContent("boom"));
  });
});
