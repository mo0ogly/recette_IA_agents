/**
 * Audit Trail page tests (R16 contract gate).
 *
 * Fixtures in __fixtures__/ were captured from the real backend after a real
 * governed flow (escalate -> approve, deny), so the events fixture carries the
 * { events: [...] } envelope and all four event kinds with a valid hash chain:
 * action_requested, action_denied, approval_resolved, action_executed.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listAuditEvents, verifyChain } from "../../api/client";
import type { ChainReport, StoredEvent } from "../../types/platform";
import eventsFixture from "./__fixtures__/events.fixture.json";
import verifyFixture from "./__fixtures__/verify.fixture.json";
import AuditPage from "./index";

vi.mock("../../api/client", () => ({
  listAuditEvents: vi.fn(),
  verifyChain: vi.fn(),
}));

const mockListAuditEvents = vi.mocked(listAuditEvents);
const mockVerifyChain = vi.mocked(verifyChain);

// The real backend wraps the list in { events: [...] } even though the client
// is typed as StoredEvent[]; the page must unwrap this envelope (R16).
const envelope = eventsFixture as unknown as StoredEvent[];
const bareEvents = (eventsFixture as unknown as { events: StoredEvent[] }).events;
const chainOk = verifyFixture as ChainReport;

const ALL_KINDS = [
  "action_requested",
  "action_denied",
  "approval_resolved",
  "action_executed",
] as const;

beforeEach(() => {
  vi.clearAllMocks();
});

/** Probe that records the current path + query into a ref for assertions. */
function LocationProbe({ sink }: { sink: { current: string } }): null {
  const location = useLocation();
  sink.current = `${location.pathname}${location.search}`;
  return null;
}

/** Render the page at a given URL, exposing the current location for assertions. */
function renderAt(initialEntry: string): RenderResult & { location: () => string } {
  const sink = { current: initialEntry };
  const result = render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuditPage />
      <LocationProbe sink={sink} />
    </MemoryRouter>,
  );
  return Object.assign(result, { location: () => sink.current });
}

describe("AuditPage", () => {
  it("shows the chain-intact banner and one row per captured event kind", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(envelope);

    renderAt("/audit");

    const banner = await screen.findByText("Chain intact (4 events verified)");
    expect(banner).toHaveClass("banner-ok");

    // Scope to the table: the kind filter <select> also lists kind names.
    const table = within(screen.getByRole("table"));
    for (const kind of ALL_KINDS) {
      expect(table.getByText(kind)).toBeInTheDocument();
    }
    expect(table.getByText("agent-bot")).toBeInTheDocument();
    expect(table.getAllByText("okta/suspend_user").length).toBeGreaterThan(0);
  });

  it("renders verdict and approval badges from the real payloads", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(envelope);

    renderAt("/audit");
    await screen.findByText("Chain intact (4 events verified)");

    const table = within(screen.getByRole("table"));
    // Verdict badge: action_denied carries policy_decision.verdict = "deny".
    const denyBadge = table.getByText("deny");
    expect(denyBadge).toHaveClass("badge", "badge-deny");
    // Verdict badge: requested/executed events carry verdict = "escalate".
    expect(table.getAllByText("escalate")[0]).toHaveClass("badge", "badge-escalate");
    // Approval badges across the flow: pending, none, approved.
    expect(table.getByText("pending")).toHaveClass("badge", "badge-pending");
    expect(table.getByText("none")).toHaveClass("badge", "badge-none");
    expect(table.getAllByText("approved")[0]).toHaveClass("badge", "badge-approved");
  });

  it("renders the allow verdict and timeout approval badges (union coverage)", async () => {
    // The captured flow never produced verdict=allow nor approval_state=timeout;
    // derive those variants from the real captured events so every
    // discriminated-union member renders (R16). Only the discriminant fields
    // and seq/event_id change.
    const base = bareEvents[0];
    const variants = {
      events: [
        {
          ...base,
          seq: 90,
          event_id: "EV-variant-allow",
          payload: {
            ...base.payload,
            policy_decision: {
              ...(base.payload.policy_decision as object),
              verdict: "allow",
            },
            approval_state: "none",
          },
        },
        {
          ...base,
          seq: 91,
          event_id: "EV-variant-timeout",
          payload: { ...base.payload, approval_state: "timeout" },
        },
      ],
    };
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(variants as unknown as StoredEvent[]);

    renderAt("/audit");
    await screen.findByText("Chain intact (4 events verified)");

    const table = within(screen.getByRole("table"));
    expect(table.getByText("allow")).toHaveClass("badge", "badge-allow");
    expect(table.getByText("timeout")).toHaveClass("badge", "badge-timeout");
  });

  it("expands a row on click and shows the pretty-printed payload JSON", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(envelope);

    const { container } = renderAt("/audit");
    await screen.findByText("Chain intact (4 events verified)");

    const table = within(screen.getByRole("table"));
    fireEvent.click(table.getByText("approval_resolved"));

    const payloadBlock = container.querySelector("pre.audit-payload");
    expect(payloadBlock).not.toBeNull();
    expect(payloadBlock).toHaveTextContent('"approver": "user:rssi"');
    expect(payloadBlock).toHaveTextContent('"reason": "ok"');

    // Clicking again collapses the detail row.
    fireEvent.click(table.getByText("approval_resolved"));
    expect(container.querySelector("pre.audit-payload")).toBeNull();
  });

  it("also accepts a bare StoredEvent[] response (client-declared shape)", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(bareEvents);

    renderAt("/audit");
    await screen.findByText("Chain intact (4 events verified)");

    const table = within(screen.getByRole("table"));
    expect(table.getByText("action_requested")).toBeInTheDocument();
  });

  it("shows a red banner with first_break_seq and detail when the chain is broken", async () => {
    mockVerifyChain.mockResolvedValue({
      ok: false,
      checked: 4,
      first_break_seq: 2,
      detail: "hash mismatch at seq 2",
    });
    mockListAuditEvents.mockResolvedValue(envelope);

    renderAt("/audit");

    const banner = await screen.findByText(/Chain broken at seq 2/);
    expect(banner).toHaveClass("banner-broken");
    expect(banner).toHaveTextContent("hash mismatch at seq 2");
    expect(screen.queryByText(/Chain intact/)).not.toBeInTheDocument();
  });

  it("shows an error banner when loading audit events fails", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockRejectedValue(new Error("network down"));

    renderAt("/audit");

    const banner = await screen.findByText(/Failed to load audit events: network down/);
    expect(banner).toHaveClass("banner-broken");
    // The chain banner is independent of the events failure.
    expect(screen.getByText("Chain intact (4 events verified)")).toBeInTheDocument();
  });

  it("shows an error banner when chain verification fails, table stays usable", async () => {
    mockVerifyChain.mockRejectedValue(new Error("verify endpoint unreachable"));
    mockListAuditEvents.mockResolvedValue(envelope);

    renderAt("/audit");

    const banner = await screen.findByText(
      /Chain verification failed: verify endpoint unreachable/,
    );
    expect(banner).toHaveClass("banner-broken");
    const table = within(screen.getByRole("table"));
    expect(table.getByText("action_executed")).toBeInTheDocument();
  });

  it("re-queries listAuditEvents with kind and agent_id params on Apply", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(envelope);

    renderAt("/audit");
    await screen.findByText("Chain intact (4 events verified)");
    expect(mockListAuditEvents).toHaveBeenCalledWith({});

    fireEvent.change(screen.getByLabelText("Kind"), {
      target: { value: "action_denied" },
    });
    fireEvent.change(screen.getByLabelText("Agent ID"), {
      target: { value: "agent-bot" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      expect(mockListAuditEvents).toHaveBeenLastCalledWith({
        kind: "action_denied",
        agent_id: "agent-bot",
      });
    });
  });

  it("filters by target_system client-side on Apply", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(envelope);

    renderAt("/audit");
    await screen.findByText("Chain intact (4 events verified)");

    fireEvent.change(screen.getByLabelText("Target system"), {
      target: { value: "no-such-system" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(
      await screen.findByText("No audit events match the current filters."),
    ).toBeInTheDocument();
  });

  it("honors ?event_id= in the URL: fetches with it and shows an active-filter chip", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(envelope);

    renderAt("/audit?event_id=EV000000000000000001000001");
    await screen.findByText("Chain intact (4 events verified)");

    expect(mockListAuditEvents).toHaveBeenCalledWith({
      event_id: "EV000000000000000001000001",
    });
    const chip = screen.getByTestId("audit-event-id-filter");
    expect(chip).toHaveTextContent("event_id: EV000000000000000001000001");
  });

  it("clears the event_id filter: navigates to /audit without the param", async () => {
    mockVerifyChain.mockResolvedValue(chainOk);
    mockListAuditEvents.mockResolvedValue(envelope);

    const view = renderAt("/audit?event_id=EV000000000000000001000001");
    await screen.findByText("Chain intact (4 events verified)");

    fireEvent.click(screen.getByRole("button", { name: "Clear event_id filter" }));

    await waitFor(() => {
      expect(view.location()).toBe("/audit");
    });
    expect(screen.queryByTestId("audit-event-id-filter")).not.toBeInTheDocument();
  });
});
