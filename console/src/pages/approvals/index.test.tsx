/**
 * R16 contract tests for the Approval Inbox page.
 *
 * Fixtures under __fixtures__/ are captured from the live recette API
 * (recette.api on port 8093 backed by the lab mock), not hand-written:
 *   - pending.fixture.json: { pending: [...] } envelope with 3 escalations
 *   - approved-outcome.fixture.json: executed=true + side_effect_hash
 *   - denied-outcome.fixture.json: executed=false, approval_state=denied
 *   - sweep.fixture.json: { timed_out: [<remaining event id>] }
 *
 * ApprovalState variant coverage (R16): "pending", "approved" and "denied"
 * are exercised here through the captured outcome fixtures, and "timeout"
 * through the sweep fixture. The "none" variant never appears in approval
 * resolutions; it is covered by the StatusBadge unit tests
 * (src/components/StatusBadge.test.tsx).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ActionOutcome, PendingApproval } from "../../types/platform";
import ApprovalsPage from "./index";
import pendingFixture from "./__fixtures__/pending.fixture.json";
import approvedFixture from "./__fixtures__/approved-outcome.fixture.json";
import deniedFixture from "./__fixtures__/denied-outcome.fixture.json";
import sweepFixture from "./__fixtures__/sweep.fixture.json";

vi.mock("../../api/client", () => ({
  listPendingApprovals: vi.fn(),
  approveAction: vi.fn(),
  denyAction: vi.fn(),
  sweepTimeouts: vi.fn(),
}));

import {
  approveAction,
  denyAction,
  listPendingApprovals,
  sweepTimeouts,
} from "../../api/client";

// The client is typed as Promise<PendingApproval[]> but the real backend
// answers with a { pending: [...] } envelope (see fixture). The mocks feed
// the page the captured payload as-is to validate the page-side unwrap.
const mockList = vi.mocked(listPendingApprovals);
const mockApprove = vi.mocked(approveAction);
const mockDeny = vi.mocked(denyAction);
const mockSweep = vi.mocked(sweepTimeouts);

const pendingEnvelope = pendingFixture as unknown as PendingApproval[];
const approvedOutcome = approvedFixture as ActionOutcome;
const deniedOutcome = deniedFixture as ActionOutcome;

const EV1 = pendingFixture.pending[0].event_id;
const EV2 = pendingFixture.pending[1].event_id;
const EV3 = pendingFixture.pending[2].event_id;

beforeEach(() => {
  vi.resetAllMocks();
  mockList.mockResolvedValue(pendingEnvelope);
});

function setApprover(value: string): void {
  fireEvent.change(screen.getByLabelText("Approver"), { target: { value } });
}

describe("ApprovalsPage inbox", () => {
  it("renders the pending items from the captured fixture", async () => {
    render(<ApprovalsPage />);

    expect(await screen.findByText("suspend_user", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByText("agent-admin").length).toBe(3);
    expect(screen.getByText("reset_password", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("modify_user_roles", { exact: false })).toBeInTheDocument();

    // Risk badge: StatusBadge kind="risk" renders the level with badge-high.
    const riskBadges = screen.getAllByText("high");
    expect(riskBadges.length).toBe(3);
    expect(riskBadges[0]).toHaveClass("badge", "badge-high");

    // Policy version is shown per item.
    expect(screen.getAllByText("policy: v1").length).toBe(3);
  });

  it("shows the empty state when there is nothing pending", async () => {
    mockList.mockResolvedValue({ pending: [] } as unknown as PendingApproval[]);
    render(<ApprovalsPage />);

    expect(await screen.findByText("No pending approvals.")).toBeInTheDocument();
  });

  it("shows an error banner and does not crash when the inbox call fails", async () => {
    mockList.mockRejectedValue(new Error("API request failed (500) on /approvals"));
    render(<ApprovalsPage />);

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("API request failed (500)");
    expect(screen.getByText("Approval Inbox")).toBeInTheDocument();
  });
});

describe("ApprovalsPage approve flow", () => {
  it("approves an item, renders the approved outcome inline and removes it from pending", async () => {
    mockApprove.mockResolvedValue(approvedOutcome);
    render(<ApprovalsPage />);
    await screen.findByText("suspend_user", { exact: false });

    setApprover("user:rssi");
    const card = screen.getByTestId(`pending-${EV1}`);
    fireEvent.click(card.querySelector("button.btn-approve") as HTMLButtonElement);

    await waitFor(() => {
      expect(screen.getByTestId(`resolved-${EV1}`)).toBeInTheDocument();
    });
    expect(mockApprove).toHaveBeenCalledWith(EV1, "user:rssi");

    // Item left the pending list.
    expect(screen.queryByTestId(`pending-${EV1}`)).not.toBeInTheDocument();

    // Inline outcome: approval badge, executed flag, truncated hash prefix.
    const resolvedCard = screen.getByTestId(`resolved-${EV1}`);
    const badge = screen.getByText("approved");
    expect(badge).toHaveClass("badge", "badge-approved");
    expect(resolvedCard).toHaveTextContent("executed: yes");
    expect(resolvedCard).toHaveTextContent("8fc323e6dc41...");
  });

  it("keeps the approve button disabled until an approver is set", async () => {
    render(<ApprovalsPage />);
    await screen.findByText("suspend_user", { exact: false });

    const card = screen.getByTestId(`pending-${EV1}`);
    const approveBtn = card.querySelector("button.btn-approve") as HTMLButtonElement;
    expect(approveBtn).toBeDisabled();
    setApprover("user:rssi");
    expect(approveBtn).not.toBeDisabled();
  });
});

describe("ApprovalsPage deny flow", () => {
  it("denies an item with a reason and renders the denied outcome", async () => {
    mockDeny.mockResolvedValue(deniedOutcome);
    render(<ApprovalsPage />);
    await screen.findByText("reset_password", { exact: false });

    setApprover("user:rssi");
    const card = screen.getByTestId(`pending-${EV2}`);
    const denyBtn = card.querySelector("button.btn-deny") as HTMLButtonElement;
    expect(denyBtn).toBeDisabled(); // reason is required to deny

    fireEvent.change(screen.getByLabelText(`Deny reason for ${EV2}`), {
      target: { value: "not justified" },
    });
    expect(denyBtn).not.toBeDisabled();
    fireEvent.click(denyBtn);

    await waitFor(() => {
      expect(screen.getByTestId(`resolved-${EV2}`)).toBeInTheDocument();
    });
    expect(mockDeny).toHaveBeenCalledWith(EV2, "user:rssi", "not justified");

    expect(screen.queryByTestId(`pending-${EV2}`)).not.toBeInTheDocument();
    const badge = screen.getByText("denied");
    expect(badge).toHaveClass("badge", "badge-denied");
    expect(screen.getByTestId(`resolved-${EV2}`)).toHaveTextContent("executed: no");
  });
});

describe("ApprovalsPage sweep flow", () => {
  it("sweeps timeouts and reports the timed-out count and ids", async () => {
    mockSweep.mockResolvedValue(sweepFixture as Record<string, unknown>);
    render(<ApprovalsPage />);
    await screen.findByText("suspend_user", { exact: false });

    // After the sweep the third escalation is no longer pending.
    mockList.mockResolvedValue({
      pending: pendingFixture.pending.filter((p) => p.event_id !== EV3),
    } as unknown as PendingApproval[]);

    fireEvent.click(screen.getByRole("button", { name: "Sweep timeouts" }));

    await waitFor(() => {
      expect(screen.getByText(`Sweep result: 1 timed out (${EV3})`)).toBeInTheDocument();
    });
    expect(mockSweep).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId(`pending-${EV3}`)).not.toBeInTheDocument();
  });
});
