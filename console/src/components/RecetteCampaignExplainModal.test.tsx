/**
 * RecetteCampaignExplainModal tests (R16 contract gate) -- render-and-assert
 * against a REAL captured GET /recette-campaigns/{id} payload
 * (__fixtures__/recetteCampaignDetail.fixture.json). The client is mocked so no
 * backend is touched; the modal must show the objective, the scored actions
 * with their expected-verdict pill, and never crash on the discriminated
 * verdict values.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ getRecetteCampaign: vi.fn() }));

import { getRecetteCampaign } from "../api/client";
import RecetteCampaignExplainModal from "./RecetteCampaignExplainModal";
import type { RecetteCampaignDetail } from "../types/platform";
import detailFixture from "./__fixtures__/recetteCampaignDetail.fixture.json";
import linkedFixture from "./__fixtures__/recetteCampaignDetailLinked.fixture.json";

const DETAIL = detailFixture as unknown as RecetteCampaignDetail;
const LINKED = linkedFixture as unknown as RecetteCampaignDetail;

afterEach(() => {
  cleanup();
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

  it("shows an Orchestration tab on a macro orchestration campaign (links present)", async () => {
    vi.mocked(getRecetteCampaign).mockResolvedValue(LINKED);
    render(<RecetteCampaignExplainModal open campaignId={LINKED.name} onClose={() => {}} />);
    await screen.findByText(LINKED.family);
    fireEvent.click(screen.getByRole("tab", { name: /Orchestration/ }));
    const links = await screen.findByTestId("rc-links");
    const link = LINKED.links?.[0];
    expect(link).toBeDefined();
    expect(within(links).getByText(link!.team)).toBeInTheDocument();
    expect(links.textContent).toContain(link!.shared_action);
    expect(links.textContent).toContain(link!.invariant ?? "I6");
  });

  it("has no Orchestration tab on a plain campaign (no links)", async () => {
    open();
    await screen.findByText(DETAIL.family);
    expect(screen.queryByRole("tab", { name: /Orchestration/ })).toBeNull();
  });
});
