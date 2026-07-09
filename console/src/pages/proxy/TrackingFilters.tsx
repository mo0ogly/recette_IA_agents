/**
 * TrackingFilters — the instance/session filter inputs for the wire panel.
 *
 * Extracted from WirePanel (size ceiling) — two text inputs that narrow the
 * buffered flows by autonomous-instance and session identity (see recette
 * tracking). Pinning an instance follows it ACROSS the sessions it acted in;
 * pinning a session scopes to one conversation/episode. Client-side + instant:
 * the values are written to the URL via setParam, exactly like the other wire
 * filters, so a filtered view is deep-linkable.
 */

import type { JSX } from "react";

export default function TrackingFilters({
  instanceId,
  sessionId,
  setParam,
}: {
  instanceId: string | undefined;
  sessionId: string | undefined;
  setParam: (key: string, value: string) => void;
}): JSX.Element {
  return (
    <>
      <label className="proxy-filter-label">
        instance
        <input
          className="proxy-filter-input"
          type="text"
          data-testid="wire-filter-instance"
          value={instanceId ?? ""}
          onChange={(e) => setParam("instance", e.target.value)}
        />
      </label>
      <label className="proxy-filter-label">
        session
        <input
          className="proxy-filter-input"
          type="text"
          data-testid="wire-filter-session"
          value={sessionId ?? ""}
          onChange={(e) => setParam("session", e.target.value)}
        />
      </label>
    </>
  );
}
