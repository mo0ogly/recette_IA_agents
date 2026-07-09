/**
 * InstanceSessionSummary — the cross-session strip for a pinned instance.
 *
 * Rendered only when an instance filter is active: shows every session that
 * instance acted in as a clickable chip (flow count + failures), so an operator
 * can follow ONE autonomous instance across its sessions and drill into any one.
 * Selecting the active session again clears it (toggle). Pure display over the
 * buffered flows; the grouping lives in wireSessionSummary (I4).
 */

import type { JSX } from "react";
import type { WireFlow } from "../../types/platform";
import { summarizeSessions } from "./wireSessionSummary";

export default function InstanceSessionSummary({
  instanceId,
  flows,
  activeSession,
  onPickSession,
}: {
  instanceId: string | undefined;
  flows: WireFlow[];
  activeSession: string | undefined;
  onPickSession: (sessionId: string) => void;
}): JSX.Element | null {
  if (!instanceId) return null;
  const sessions = summarizeSessions(flows);
  if (sessions.length === 0) return null;
  return (
    <div className="wire-instance-sessions" data-testid="wire-instance-sessions">
      <span className="wire-instance-sessions-title">
        instance <code>{instanceId}</code> — {sessions.length} session(s)
      </span>
      <div className="wire-instance-sessions-chips">
        {sessions.map((s) => (
          <button
            key={s.sessionId}
            type="button"
            className={
              "wire-session-chip" + (s.sessionId === activeSession ? " is-active" : "")
            }
            onClick={() => onPickSession(s.sessionId === activeSession ? "" : s.sessionId)}
            title={`seq ${s.firstSeq}..${s.lastSeq}`}
          >
            {s.sessionId.slice(0, 12)} · {s.count}
            {s.fails > 0 ? ` · ${s.fails} echec(s)` : ""}
          </button>
        ))}
      </div>
    </div>
  );
}
