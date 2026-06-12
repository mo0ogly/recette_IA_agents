/**
 * LogConsole -- reusable presentational log window (dark, monospace).
 *
 * Pure component: the caller owns the lines (e.g. from useAuditTail).
 * Features: substring filter, pause (freezes a snapshot, resume shows
 * everything), copy of the visible lines, autoscroll to the bottom unless
 * the user scrolled up, line count badge, empty state.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { AuditEvent } from "../types/platform";
import "./LogConsole.css";

export interface LogLine {
  seq: number;
  level: "info" | "warn" | "error";
  source: string;
  text: string;
}

export interface LogConsoleProps {
  title: string;
  lines: LogLine[];
  onClear?: () => void;
}

/** Pixels from the bottom under which autoscroll stays engaged. */
const AUTOSCROLL_SLACK_PX = 24;

/**
 * Map one audited event to a displayable log line.
 *
 * Level keys off fields that exist in the real /audit/events payloads:
 * - platform_error events (audited internal failures) -> "error";
 * - policy_decision.verdict "deny", or an approval resolved as denied or
 *   timed out -> "warn";
 * - everything else (allow, escalate -> pending, approved) -> "info".
 * Source is the acting agent, or "platform" for agent-less records.
 */
export function auditEventToLogLine(e: AuditEvent): LogLine {
  const p = e.payload;
  let level: LogLine["level"] = "info";
  if (e.kind === "platform_error") {
    level = "error";
  } else if (
    p.policy_decision?.verdict === "deny" ||
    p.approval_state === "denied" ||
    p.approval_state === "timeout"
  ) {
    level = "warn";
  }

  const action =
    p.target_system !== undefined && p.action_type !== undefined
      ? `${p.target_system}/${p.action_type}`
      : (p.target_system ?? p.action_type);
  const parts: string[] = [e.kind];
  if (action !== undefined) {
    parts.push(action);
  }
  if (p.resource !== undefined) {
    parts.push(p.resource);
  }
  if (p.approval_state !== undefined && p.approval_state !== "none") {
    parts.push(`approval=${p.approval_state}`);
  }
  if (p.policy_decision != null) {
    parts.push(`verdict=${p.policy_decision.verdict}`);
  }

  return {
    seq: e.seq,
    level,
    source: p.agent_id ?? "platform",
    text: parts.join(" "),
  };
}

export function LogConsole({ title, lines, onClear }: LogConsoleProps): JSX.Element {
  const [filter, setFilter] = useState("");
  const [frozen, setFrozen] = useState<LogLine[] | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);

  const paused = frozen !== null;
  const base = frozen ?? lines;

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (needle.length === 0) {
      return base;
    }
    return base.filter(
      (l) =>
        l.text.toLowerCase().includes(needle) || l.source.toLowerCase().includes(needle),
    );
  }, [base, filter]);

  useEffect(() => {
    const el = bodyRef.current;
    if (el !== null && stickToBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [visible.length]);

  const handleScroll = (): void => {
    const el = bodyRef.current;
    if (el === null) {
      return;
    }
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom <= AUTOSCROLL_SLACK_PX;
  };

  const togglePause = (): void => {
    setFrozen(paused ? null : [...lines]);
  };

  const copyVisible = (): void => {
    const text = visible.map((l) => `${l.seq} [${l.level}] ${l.source} ${l.text}`).join("\n");
    void navigator.clipboard.writeText(text);
  };

  return (
    <section className="logc">
      <header className="logc-header">
        <span className="logc-title">{title}</span>
        <span className="logc-count">{visible.length} lines</span>
        <input
          className="logc-filter"
          type="text"
          placeholder="filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button type="button" className="logc-btn" onClick={togglePause}>
          {paused ? "Resume" : "Pause"}
        </button>
        <button type="button" className="logc-btn" onClick={copyVisible}>
          Copy
        </button>
        {onClear !== undefined && (
          <button type="button" className="logc-btn" onClick={onClear}>
            Clear
          </button>
        )}
      </header>
      <div className="logc-body" ref={bodyRef} onScroll={handleScroll}>
        {visible.length === 0 ? (
          <div className="logc-empty">no log lines</div>
        ) : (
          visible.map((line) => (
            <div className="logc-line" data-level={line.level} key={line.seq}>
              <span className="logc-seq">{line.seq}</span>
              <span className="logc-source">{line.source}</span>
              <span className="logc-text">{line.text}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
