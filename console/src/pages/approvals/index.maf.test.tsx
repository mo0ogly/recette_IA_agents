/**
 * R16 contract test: the existing Approval Inbox renders a MAF gated tool
 * approval. A MAF agent invoking an MCP tool escalates through the platform's
 * I6 workflow and surfaces in /approvals like any other pending action -- the
 * page needs no MAF-specific code. Fixture captured from the live gateway
 * (mcp / invoke_tool, HIGH risk).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PendingApproval } from "../../types/platform";
import ApprovalsPage from "./index";
import mafFixture from "./__fixtures__/mafApproval.fixture.json";

vi.mock("../../api/client", () => ({
  listPendingApprovals: vi.fn(),
  approveAction: vi.fn(),
  denyAction: vi.fn(),
  sweepTimeouts: vi.fn(),
}));

import { listPendingApprovals, sweepTimeouts } from "../../api/client";

const mockList = vi.mocked(listPendingApprovals);
const mockSweep = vi.mocked(sweepTimeouts);

const mafEnvelope = mafFixture as unknown as PendingApproval[];
const MAF = mafFixture.pending[0];

describe("ApprovalsPage -- MAF gated tool approval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue(mafEnvelope);
    mockSweep.mockResolvedValue({ timed_out: [] } as never);
  });

  it("renders the MAF mcp/invoke_tool approval from a real gateway payload", async () => {
    render(<ApprovalsPage />);
    const card = await screen.findByTestId(`pending-${MAF.event_id}`);
    expect(card).toBeInTheDocument();
    // target_system / action_type surfaced by the generic approval card.
    expect(card).toHaveTextContent("mcp");
    expect(card).toHaveTextContent("invoke_tool");
    expect(card).toHaveTextContent(MAF.agent_id);
  });

  it("exposes Approve and Deny controls for the gated action (I6)", async () => {
    render(<ApprovalsPage />);
    await waitFor(() => expect(screen.getByText("Approve")).toBeInTheDocument());
    expect(screen.getByText("Deny")).toBeInTheDocument();
  });
});
