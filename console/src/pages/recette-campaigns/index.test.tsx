/**
 * Recette campaigns page tests (R16 contract gate) -- render-and-assert against
 * a REAL captured GET /recette-campaigns payload
 * (__fixtures__/recetteCampaigns.fixture.json). The client is mocked; the page
 * must list the campaigns with their family + counts and expose an "Expliquer"
 * eye per valid row.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", () => ({
  listRecetteCampaigns: vi.fn(),
  getRecetteCampaign: vi.fn(),
}));

import { listRecetteCampaigns } from "../../api/client";
import RecetteCampaignsPage from "./index";
import type { RecetteCampaignSummary } from "../../types/platform";
import fixture from "./__fixtures__/recetteCampaigns.fixture.json";

const CAMPAIGNS = fixture as unknown as RecetteCampaignSummary[];

afterEach(() => {
  vi.clearAllMocks();
});

function renderPage(): void {
  render(
    <MemoryRouter>
      <RecetteCampaignsPage />
    </MemoryRouter>,
  );
}

describe("RecetteCampaignsPage", () => {
  it("lists every campaign with an Expliquer eye", async () => {
    vi.mocked(listRecetteCampaigns).mockResolvedValue(CAMPAIGNS);
    renderPage();
    const table = await screen.findByTestId("rc-table");
    const rows = within(table).getAllByRole("row");
    // header + one row per campaign.
    expect(rows.length).toBe(CAMPAIGNS.length + 1);
    // The first valid campaign exposes its Explain eye (aria-label by id).
    const firstValid = CAMPAIGNS.find((c) => c.error === undefined);
    expect(firstValid).toBeDefined();
    expect(
      screen.getByRole("button", { name: `Expliquer ${firstValid!.id}` }),
    ).toBeInTheDocument();
  });

  it("badges a macro orchestration campaign (linked=true)", async () => {
    vi.mocked(listRecetteCampaigns).mockResolvedValue(CAMPAIGNS);
    renderPage();
    const linked = CAMPAIGNS.find((c) => c.linked === true);
    expect(linked).toBeDefined();
    expect(await screen.findByTestId(`rc-linked-${linked!.id}`)).toHaveTextContent(
      "orchestration",
    );
    // A non-linked campaign carries no badge.
    const plain = CAMPAIGNS.find((c) => c.linked !== true && c.error === undefined);
    expect(plain).toBeDefined();
    expect(screen.queryByTestId(`rc-linked-${plain!.id}`)).toBeNull();
  });

  it("surfaces a fetch error", async () => {
    vi.mocked(listRecetteCampaigns).mockRejectedValue(new Error("no catalog"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("no catalog");
  });

  it("shows the empty state when the catalog is empty", async () => {
    vi.mocked(listRecetteCampaigns).mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(screen.getByTestId("rc-empty")).toBeInTheDocument());
  });
});
