import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RunsExplorer from "./index";
import {
  fetchRunTree,
  fetchRun,
  fetchRunArtifact,
  patchRunAnnotations,
  deleteRun,
  replayRun,
} from "../../api/client";
import type { RunDetail, RunTree } from "../../api/client";
import treeFixture from "./__fixtures__/runs-tree.fixture.json";
import detailFixture from "./__fixtures__/run-detail.fixture.json";

// Mock ALL client functions used by this page (a missing mock will throw).
vi.mock("../../api/client", () => ({
  fetchRunTree: vi.fn(),
  fetchRun: vi.fn(),
  fetchRunArtifact: vi.fn(),
  patchRunAnnotations: vi.fn(),
  deleteRun: vi.fn(),
  replayRun: vi.fn(),
}));

// Monaco is heavy and worker-bound; stub so assertions work in jsdom.
vi.mock("../../components/MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => (
    <pre data-testid="monaco-stub">{value}</pre>
  ),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("RunsExplorer", () => {
  it("renders the treeview on mount", async () => {
    vi.mocked(fetchRunTree).mockResolvedValue(treeFixture as RunTree);
    vi.mocked(fetchRun).mockResolvedValue(detailFixture as RunDetail);
    vi.mocked(fetchRunArtifact).mockResolvedValue('{"ok":true}');
    render(<RunsExplorer />);

    // Tree should appear with the category from the fixture
    expect(await screen.findByTestId("run-category-skynet")).toBeInTheDocument();
    expect(screen.getByTestId("run-group-megacamp-demo")).toBeInTheDocument();
    expect(screen.getByTestId("run-node-agents-fleet")).toBeInTheDocument();
  });

  it("fetches run detail and shows artifact content + Meta tab after selecting a run", async () => {
    vi.mocked(fetchRunTree).mockResolvedValue(treeFixture as RunTree);
    vi.mocked(fetchRun).mockResolvedValue(detailFixture as RunDetail);
    vi.mocked(fetchRunArtifact).mockResolvedValue('{"agent_id":"a","ok":true}');
    render(<RunsExplorer />);

    await screen.findByTestId("run-category-skynet");

    // Click on a run
    const runBtn = screen
      .getByTestId("run-node-agents-fleet")
      .querySelector("button")!;
    fireEvent.click(runBtn);

    // Monaco shows artifact content
    const monacoStub = await screen.findByTestId("monaco-stub");
    expect(monacoStub.textContent).toContain("agent_id");

    // Switch to Meta tab and check root_hash
    fireEvent.click(screen.getByTestId("runs-tab-meta"));
    expect(await screen.findByTestId("meta-root-hash")).toHaveTextContent(
      (detailFixture as RunDetail).meta.root_hash,
    );
  });

  it("calls patchRunAnnotations on save from Annotations tab", async () => {
    vi.mocked(fetchRunTree).mockResolvedValue(treeFixture as RunTree);
    vi.mocked(fetchRun).mockResolvedValue(detailFixture as RunDetail);
    vi.mocked(fetchRunArtifact).mockResolvedValue('{}');
    vi.mocked(patchRunAnnotations).mockResolvedValue(detailFixture as RunDetail);
    render(<RunsExplorer />);

    await screen.findByTestId("run-category-skynet");
    fireEvent.click(
      screen.getByTestId("run-node-agents-fleet").querySelector("button")!,
    );

    // Switch to Annotations tab
    fireEvent.click(await screen.findByTestId("runs-tab-annotations"));

    // Edit comment
    const commentInput = await screen.findByTestId("annot-comment-input");
    fireEvent.change(commentInput, { target: { value: "test comment" } });

    // Save
    fireEvent.click(screen.getByTestId("annot-save-btn"));

    await waitFor(() =>
      expect(vi.mocked(patchRunAnnotations)).toHaveBeenCalledWith(
        "agents-fleet",
        expect.objectContaining({ comment: "test comment" }),
      ),
    );
    expect(await screen.findByTestId("annot-saved")).toBeInTheDocument();
  });

  it("calls deleteRun after confirm dialog", async () => {
    vi.mocked(fetchRunTree).mockResolvedValue(treeFixture as RunTree);
    vi.mocked(fetchRun).mockResolvedValue(detailFixture as RunDetail);
    vi.mocked(fetchRunArtifact).mockResolvedValue('{}');
    vi.mocked(deleteRun).mockResolvedValue(undefined);
    // After delete tree is re-fetched
    vi.mocked(fetchRunTree)
      .mockResolvedValueOnce(treeFixture as RunTree)
      .mockResolvedValue({ categories: [] } as RunTree);
    render(<RunsExplorer />);

    await screen.findByTestId("run-category-skynet");
    fireEvent.click(
      screen.getByTestId("run-node-agents-fleet").querySelector("button")!,
    );

    // Open confirm dialog
    fireEvent.click(await screen.findByTestId("runs-delete-btn"));
    expect(await screen.findByTestId("runs-confirm-dialog")).toBeInTheDocument();

    // Confirm
    fireEvent.click(screen.getByTestId("runs-confirm-ok"));

    await waitFor(() =>
      expect(vi.mocked(deleteRun)).toHaveBeenCalledWith("agents-fleet"),
    );
  });

  it("calls replayRun when Replay button is clicked", async () => {
    // Real /results/{id}/replay response shape (verified live, 201):
    // { child_run_id, replay_of, status, kind } -- NOT a full RunDetail.
    const replayChild = {
      child_run_id: "agents-fleet-replay",
      replay_of: "agents-fleet",
      status: "running",
      kind: "agent",
    };
    vi.mocked(fetchRunTree).mockResolvedValue(treeFixture as RunTree);
    vi.mocked(fetchRun).mockResolvedValue(detailFixture as RunDetail);
    vi.mocked(fetchRunArtifact).mockResolvedValue('{}');
    vi.mocked(replayRun).mockResolvedValue(replayChild);
    render(<RunsExplorer />);

    await screen.findByTestId("run-category-skynet");
    fireEvent.click(
      screen.getByTestId("run-node-agents-fleet").querySelector("button")!,
    );

    // Switch to Replay tab
    fireEvent.click(await screen.findByTestId("runs-tab-replay"));
    fireEvent.click(await screen.findByTestId("replay-btn"));

    await waitFor(() =>
      expect(vi.mocked(replayRun)).toHaveBeenCalledWith("agents-fleet"),
    );
    expect(await screen.findByTestId("replay-result")).toHaveTextContent(
      "agents-fleet-replay",
    );
  });

  it("handles 422 from replayRun gracefully", async () => {
    vi.mocked(fetchRunTree).mockResolvedValue(treeFixture as RunTree);
    vi.mocked(fetchRun).mockResolvedValue(detailFixture as RunDetail);
    vi.mocked(fetchRunArtifact).mockResolvedValue('{}');
    vi.mocked(replayRun).mockRejectedValue(new Error("422 not replayable"));
    render(<RunsExplorer />);

    await screen.findByTestId("run-category-skynet");
    fireEvent.click(
      screen.getByTestId("run-node-agents-fleet").querySelector("button")!,
    );

    fireEvent.click(await screen.findByTestId("runs-tab-replay"));
    fireEvent.click(await screen.findByTestId("replay-btn"));

    expect(await screen.findByTestId("replay-error")).toHaveTextContent(
      "n'est pas rejouable",
    );
  });
});
