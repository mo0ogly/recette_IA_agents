/**
 * Tests for the Cockpit page global audit console.
 *
 * auditEvents.fixture.json was captured from a live GET /audit/events;
 * logLines.fixture.json is the committed derivation of those events through
 * auditEventToLogLine. The cockpit mounts an unfiltered useAuditTail and
 * renders every audited platform event in the "Platform audit" LogConsole.
 */

import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import auditFixture from "../../hooks/__fixtures__/auditEvents.fixture.json";
import linesFixture from "../../components/__fixtures__/logLines.fixture.json";
import type { LogLine } from "../../components/LogConsole";
import type { AuditEvent } from "../../types/platform";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listAgents: vi.fn(),
    listAiBackends: vi.fn(),
    launchLaneB: vi.fn(),
    openRunSocket: vi.fn(),
    stopRun: vi.fn(),
    listAuditEvents: vi.fn(),
  };
});

import { listAgents, listAiBackends, listAuditEvents } from "../../api/client";
import CockpitPage from "./index";

const auditEvents = (auditFixture as unknown as { events: AuditEvent[] }).events;
const fixtureLines = linesFixture as LogLine[];

describe("CockpitPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("tails the unfiltered audit log into the Platform audit console", async () => {
    vi.mocked(listAgents).mockResolvedValue([]);
    vi.mocked(listAiBackends).mockResolvedValue([]);
    // First poll returns the captured batch; later polls are empty.
    vi.mocked(listAuditEvents)
      .mockResolvedValueOnce(auditEvents)
      .mockResolvedValue([]);

    render(<CockpitPage />);

    expect(screen.getByText("Platform audit")).toBeInTheDocument();

    // Every captured event renders as one console line (text from the
    // committed derived fixture, so the mapping cannot drift silently).
    for (const line of fixtureLines) {
      expect(await screen.findByText(line.text)).toBeInTheDocument();
    }
    // The tail is unfiltered: the first poll starts at the beginning with a
    // bounded backfill (only the last maxEvents matter to a live tail).
    expect(listAuditEvents).toHaveBeenCalledWith({
      from_seq: 0,
      tail: 2000,
      agent_id: undefined,
      target_system: undefined,
      kind: undefined,
    });

    // seq 1 is an action_denied event (verdict deny) -> warn-level row.
    const denied = fixtureLines.find((l) => l.text.startsWith("action_denied"));
    const warnRow = screen.getByText(denied!.text).closest(".logc-line");
    expect(warnRow).toHaveAttribute("data-level", "warn");
    // seq 2 is an escalate -> pending request, informational.
    const requested = fixtureLines.find((l) => l.text.startsWith("action_requested"));
    const infoRow = screen.getByText(requested!.text).closest(".logc-line");
    expect(infoRow).toHaveAttribute("data-level", "info");
  });

  it("surfaces the stalled badge after consecutive audit poll failures", async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(listAgents).mockResolvedValue([]);
      vi.mocked(listAiBackends).mockResolvedValue([]);
      vi.mocked(listAuditEvents).mockRejectedValue(new Error("backend down"));

      render(<CockpitPage />);
      expect(screen.queryByText("stalled")).not.toBeInTheDocument();

      // Default interval 1500 ms: poll at t=0, 1500, 3000 -> third failure.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3100);
      });
      expect(screen.getByText("stalled")).toBeInTheDocument();

      // First successful poll clears the badge.
      vi.mocked(listAuditEvents).mockResolvedValue([]);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
      expect(screen.queryByText("stalled")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
