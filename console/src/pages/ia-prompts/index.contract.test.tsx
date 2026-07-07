/**
 * R16 contract tests for the Prompts IA page.
 *
 * The fixture (../../components/assist/__fixtures__/assistPrompts.fixture.json)
 * was captured from the REAL docker API (GET /assist/prompts, 9 catalog
 * entries covering both kind variants text AND json). The assist client is
 * mocked so the page renders against the exact payload shape.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AssistPromptsResponse } from "../../types/assist";

import promptsFixture from "../../components/assist/__fixtures__/assistPrompts.fixture.json";

vi.mock("../../api/assistClient", () => ({
  listAssistPrompts: vi.fn(),
  setAssistPrompt: vi.fn(),
  resetAssistPrompt: vi.fn(),
}));

import { listAssistPrompts, resetAssistPrompt, setAssistPrompt } from "../../api/assistClient";

import IaPromptsPage from "./index";

const fixture = promptsFixture as AssistPromptsResponse;

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={["/ia-prompts"]}>
      <IaPromptsPage />
    </MemoryRouter>,
  );
}

describe("IaPromptsPage (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAssistPrompts).mockResolvedValue(fixture);
    vi.mocked(resetAssistPrompt).mockResolvedValue(undefined);
  });

  it("renders every catalog entry from the real payload, grouped by view", async () => {
    renderPage();
    await screen.findByText("Copilote IA -- instructions systeme du chat");
    for (const entry of fixture.prompts) {
      expect(screen.getByText(entry.id)).toBeInTheDocument();
    }
    // Both kind variants of the union render.
    const kinds = new Set(fixture.prompts.map((p) => p.kind));
    expect(kinds).toContain("text");
    expect(kinds).toContain("json");
    // Grouped by localisation.view (one section per distinct view).
    const views = new Set(fixture.prompts.map((p) => p.localisation.view));
    for (const view of views) {
      expect(screen.getByTestId(`iaprompts-group-${view.replace(/\//g, "")}`)).toBeInTheDocument();
    }
  });

  it("marks default entries and disables their reset button", async () => {
    renderPage();
    await screen.findByText("chat.system");
    // Fixture captured with zero overrides: every row shows "defaut".
    expect(screen.getAllByText("defaut").length).toBe(fixture.prompts.length);
    for (const button of screen.getAllByRole("button", { name: "Reinitialiser" })) {
      expect(button).toBeDisabled();
    }
  });

  it("shows the overridden badge and resets through the API", async () => {
    const overridden: AssistPromptsResponse = {
      prompts: fixture.prompts.map((p) =>
        p.id === "chat.system" ? { ...p, value: "custom", overridden: true } : p,
      ),
    };
    vi.mocked(listAssistPrompts).mockResolvedValue(overridden);
    renderPage();
    await screen.findByText("modifie");
    const resetButtons = screen.getAllByRole("button", { name: "Reinitialiser" });
    const enabled = resetButtons.filter((b) => !(b as HTMLButtonElement).disabled);
    expect(enabled).toHaveLength(1);
    fireEvent.click(enabled[0]);
    await waitFor(() => expect(resetAssistPrompt).toHaveBeenCalledWith("chat.system"));
    // The catalog is reloaded after a reset.
    await waitFor(() => expect(listAssistPrompts).toHaveBeenCalledTimes(2));
  });

  it("opens the edit modal on Modifier and saves through the API", async () => {
    const entry = fixture.prompts.find((p) => p.id === "chat.system");
    expect(entry).toBeDefined();
    vi.mocked(setAssistPrompt).mockResolvedValue({
      ...entry!,
      value: "nouveau prompt",
      overridden: true,
    });
    renderPage();
    await screen.findByText("chat.system");
    const row = screen.getByText("chat.system").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(row!.querySelector("button")!);
    // Modal opens on the entry (Monaco is lazy; assert the dialog frame).
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAttribute("aria-label", `Modifier ${entry!.label}`);
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() =>
      expect(setAssistPrompt).toHaveBeenCalledWith("chat.system", entry!.value),
    );
    // Modal closes and the catalog reloads.
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(listAssistPrompts).toHaveBeenCalledTimes(2));
  });
});
