/**
 * RecetteCampaignExplainModal tests (R16 contract gate) -- render-and-assert
 * against a REAL captured GET /recette-campaigns/{id} payload
 * (__fixtures__/recetteCampaignDetail.fixture.json). The client is mocked so no
 * backend is touched; the modal must show the objective, the scored actions
 * with their expected-verdict pill, and never crash on the discriminated
 * verdict values.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getRecetteCampaign: vi.fn() }));

import { getRecetteCampaign } from "../api/client";
import RecetteCampaignExplainModal from "./RecetteCampaignExplainModal";
import type { RecetteCampaignDetail } from "../types/platform";
import detailFixture from "./__fixtures__/recetteCampaignDetail.fixture.json";

const DETAIL = detailFixture as unknown as RecetteCampaignDetail;

afterEach(() => {
  vi.clearAllMocks();
});

function open(): void {
  vi.mocked(getRecetteCampaign).mockResolvedValue(DETAIL);
  render(
    <RecetteCampaignExplainModal open campaignId={DETAIL.name} onClose={() => {}} />,
  );
}

describe("RecetteCampaignExplainModal", () => {
  it("renders objective + actions with their expected-verdict pill", async () => {
    open();
    // Wait for the loaded modal: the Objectif tab content (campaign family) is
    // shown first, which proves the detail resolved and tabs are stable.
    await screen.findByText(DETAIL.family);
    fireEvent.click(screen.getByRole("tab", { name: /Actions/ }));
    const list = await screen.findByTestId("rc-actions");
    // The first action's type, target and expected verdict are surfaced.
    const first = DETAIL.actions[0];
    expect(within(list).getByText(first.action_type)).toBeInTheDocument();
    expect(list.textContent).toContain(first.target_system);
    if (first.expect !== undefined) {
      expect(list.textContent).toContain(first.expect);
    }
  });

  it("fetches the detail for the opened campaign id", async () => {
    open();
    await waitFor(() =>
      expect(vi.mocked(getRecetteCampaign)).toHaveBeenCalledWith(DETAIL.name),
    );
  });

  it("surfaces a load error without crashing", async () => {
    vi.mocked(getRecetteCampaign).mockRejectedValue(new Error("catalog down"));
    render(<RecetteCampaignExplainModal open campaignId="x" onClose={() => {}} />);
    expect(await screen.findByText(/catalog down/)).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    render(<RecetteCampaignExplainModal open={false} campaignId="x" onClose={() => {}} />);
    expect(screen.queryByRole("tab")).toBeNull();
  });
});
