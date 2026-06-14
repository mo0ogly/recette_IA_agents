import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import KnowledgeBaseManager from "./KnowledgeBaseManager";
import {
  listKbDocuments,
  listRagScenarios,
  type KbDocument,
} from "../../api/client";
import docsFixture from "./__fixtures__/kbDocuments.fixture.json";
import scenariosFixture from "./__fixtures__/kbScenarios.fixture.json";

vi.mock("../../api/client", () => ({
  listKbDocuments: vi.fn(),
  listRagScenarios: vi.fn(),
  resetKb: vi.fn(),
  applyRagScenario: vi.fn(),
  addKbDocument: vi.fn(),
  deleteKbDocument: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("KnowledgeBaseManager", () => {
  it("renders one row per document and flags poisoned docs from a real payload", async () => {
    vi.mocked(listKbDocuments).mockResolvedValue(docsFixture.documents as KbDocument[]);
    vi.mocked(listRagScenarios).mockResolvedValue(scenariosFixture.scenarios);
    render(<KnowledgeBaseManager />);

    const rows = await screen.findAllByTestId("kb-row");
    expect(rows).toHaveLength(docsFixture.documents.length);
    expect(screen.getByText("Employee onboarding checklist")).toBeInTheDocument();

    // At least one poisoned doc renders its threat in a fail pill.
    const poisoned = docsFixture.documents.filter((d) => d.poisoned);
    expect(poisoned.length).toBeGreaterThan(0);
    expect(screen.getByText(`poison: ${poisoned[0].threat}`)).toBeInTheDocument();

    // Operator controls are present.
    expect(screen.getByTestId("kb-reset")).toBeInTheDocument();
    expect(screen.getByTestId("kb-apply")).toBeInTheDocument();
    expect(screen.getByTestId("kb-scenario-select")).toBeInTheDocument();
  });

  it("shows an inline error when the load fails", async () => {
    vi.mocked(listKbDocuments).mockRejectedValue(new Error("kb down"));
    vi.mocked(listRagScenarios).mockResolvedValue([]);
    render(<KnowledgeBaseManager />);
    await waitFor(() =>
      expect(screen.getByTestId("kb-error")).toHaveTextContent("kb down"),
    );
  });

  it("renders an empty state when the knowledge base has no documents", async () => {
    vi.mocked(listKbDocuments).mockResolvedValue([]);
    vi.mocked(listRagScenarios).mockResolvedValue([]);
    render(<KnowledgeBaseManager />);
    expect(
      await screen.findByText("The knowledge base is empty."),
    ).toBeInTheDocument();
  });
});
