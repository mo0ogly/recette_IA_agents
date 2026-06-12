/**
 * LogConsole tests.
 *
 * logLines.fixture.json is DERIVED from the real audit fixture
 * (src/hooks/__fixtures__/auditEvents.fixture.json, captured from a live
 * GET /audit/events) by mapping each event through auditEventToLogLine.
 * One test re-derives the lines at run time and asserts the committed
 * fixture matches, so the derivation can never drift silently.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import auditFixture from "../hooks/__fixtures__/auditEvents.fixture.json";
import type { AuditEvent } from "../types/platform";
import linesFixture from "./__fixtures__/logLines.fixture.json";
import { auditEventToLogLine, LogConsole, type LogLine } from "./LogConsole";

const auditEvents = (auditFixture as unknown as { events: AuditEvent[] }).events;
const fixtureLines = linesFixture as LogLine[];

// LogConsole is purely presentational; an error-level line is a legal prop
// value (it is what auditEventToLogLine produces for platform_error events).
const errorLine: LogLine = {
  seq: 99,
  level: "error",
  source: "platform",
  text: "platform_error okta/suspend_user users/jdoe",
};

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  writeText.mockClear();
  Object.assign(navigator, { clipboard: { writeText } });
});

describe("auditEventToLogLine", () => {
  it("derives the committed fixture from the real audit events", () => {
    expect(auditEvents.length).toBeGreaterThanOrEqual(2);
    const derived = auditEvents.map(auditEventToLogLine);
    expect(derived).toEqual(fixtureLines);
  });

  it("maps deny and denied-approval events to warn, others to info", () => {
    const bySeq = new Map(fixtureLines.map((l) => [l.seq, l]));
    // seq 1: action_denied (policy_decision.verdict = deny).
    expect(bySeq.get(1)?.level).toBe("warn");
    // seq 2: action_requested (escalate -> pending), informational.
    expect(bySeq.get(2)?.level).toBe("info");
    // seq 3: approval_resolved with approval_state = denied.
    expect(bySeq.get(3)?.level).toBe("warn");
  });

  it("uses agent_id as source and falls back to platform", () => {
    expect(fixtureLines[0].source).toBe("fixture-bot");
    const anonymous = auditEventToLogLine({
      ...auditEvents[0],
      payload: { ...auditEvents[0].payload, agent_id: undefined },
    });
    expect(anonymous.source).toBe("platform");
  });
});

describe("LogConsole", () => {
  it("renders one row per line plus a count badge", () => {
    render(<LogConsole title="Audit tail" lines={fixtureLines} />);

    expect(screen.getByText("Audit tail")).toBeInTheDocument();
    const rows = document.querySelectorAll(".logc-line");
    expect(rows).toHaveLength(fixtureLines.length);
    expect(screen.getByText(`${fixtureLines.length} lines`)).toBeInTheDocument();
    expect(screen.getByText(fixtureLines[0].text)).toBeInTheDocument();
  });

  it("marks error lines with data-level=error", () => {
    render(<LogConsole title="t" lines={[...fixtureLines, errorLine]} />);

    const row = screen.getByText(errorLine.text).closest(".logc-line");
    expect(row).toHaveAttribute("data-level", "error");
    const infoRow = screen.getByText(fixtureLines[1].text).closest(".logc-line");
    expect(infoRow).toHaveAttribute("data-level", "info");
  });

  it("filters lines by substring", () => {
    render(<LogConsole title="t" lines={fixtureLines} />);

    fireEvent.change(screen.getByPlaceholderText("filter"), {
      target: { value: "approval_resolved" },
    });
    expect(document.querySelectorAll(".logc-line")).toHaveLength(1);
    expect(screen.getByText("1 lines")).toBeInTheDocument();
  });

  it("pause freezes the visible snapshot; resume shows everything", () => {
    const { rerender } = render(<LogConsole title="t" lines={fixtureLines} />);

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    rerender(<LogConsole title="t" lines={[...fixtureLines, errorLine]} />);
    // Frozen: the line added while paused is not shown.
    expect(document.querySelectorAll(".logc-line")).toHaveLength(fixtureLines.length);
    expect(screen.queryByText(errorLine.text)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    expect(document.querySelectorAll(".logc-line")).toHaveLength(fixtureLines.length + 1);
    expect(screen.getByText(errorLine.text)).toBeInTheDocument();
  });

  it("copies the visible filtered lines to the clipboard, one per line", () => {
    render(<LogConsole title="t" lines={fixtureLines} />);

    fireEvent.change(screen.getByPlaceholderText("filter"), {
      target: { value: "action_denied" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    expect(writeText).toHaveBeenCalledTimes(1);
    const copied = writeText.mock.calls[0][0] as string;
    const copiedLines = copied.split("\n");
    expect(copiedLines).toHaveLength(1);
    expect(copiedLines[0]).toContain("action_denied");
    expect(copied).not.toContain("approval_resolved");
  });

  it("shows the empty state when there are no lines", () => {
    render(<LogConsole title="t" lines={[]} />);
    expect(screen.getByText("no log lines")).toBeInTheDocument();
  });

  it("calls onClear when the clear button is pressed", () => {
    const onClear = vi.fn();
    render(<LogConsole title="t" lines={fixtureLines} onClear={onClear} />);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
