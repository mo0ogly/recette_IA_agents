/**
 * R16 contract test: the Control plane page renders the architecture diagram +
 * the live governance digest against a REAL captured /control/summary payload.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import summaryFixture from "./__fixtures__/summary.fixture.json";
import type { ControlSummary } from "../../types/platform";

vi.mock("../../api/client", () => ({ getControlSummary: vi.fn() }));

import { getControlSummary } from "../../api/client";
import ControlPage from "./index";

const summary = summaryFixture as unknown as ControlSummary;

describe("ControlPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the 3-plane diagram and the live verdict/approval/execution digest", async () => {
    vi.mocked(getControlSummary).mockResolvedValue(summary);

    render(<ControlPage />);

    // The architecture diagram is always present (Mermaid renders its raw source
    // in jsdom, test-safe). Deny-by-default is the Control plane's posture.
    expect(screen.getByText(/Control plane -- decide/)).toBeInTheDocument();

    // The live digest renders from the real payload.
    const digest = await screen.findByTestId("control-summary");
    // Verdict counts from the fixture are surfaced (allow + deny + escalate cards).
    expect(within(digest).getByText(String(summary.verdicts.deny))).toBeInTheDocument();
    expect(within(digest).getByText("deny")).toBeInTheDocument();
    expect(within(digest).getByText("escalate")).toBeInTheDocument();
    // Deny-by-default posture is shown when the backend reports it.
    if (summary.deny_by_default) {
      expect(await screen.findByTestId("control-deny-by-default")).toBeInTheDocument();
    }
  });

  it("shows the help trigger for the control topic", () => {
    vi.mocked(getControlSummary).mockResolvedValue(summary);
    render(<ControlPage />);
    expect(screen.getByRole("button", { name: /Aide/ })).toBeInTheDocument();
  });

  it("surfaces a load error without crashing the page", async () => {
    vi.mocked(getControlSummary).mockRejectedValue(new Error("control down"));
    render(<ControlPage />);
    await waitFor(() => expect(screen.getByText(/control down/)).toBeInTheDocument());
    // The architecture diagram still renders (concept is static, not data-bound).
    expect(screen.getByText(/Control plane -- decide/)).toBeInTheDocument();
  });
});
