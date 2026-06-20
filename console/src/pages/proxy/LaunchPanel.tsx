/**
 * Mini-launcher for the proxy page.
 *
 * One screen to "launch and watch it in the proxy": pick a runtime agent, launch
 * it, and let the page auto-switch to the sessions source preselected on that run
 * (SessionsPanel reads ?run=). The panel owns only its local selection state; it
 * reports the resulting run id through onLaunched and lets the parent page own
 * the URL (it sets ?source=sessions&run=<run_id>).
 *
 * Agent-only by design: a replayed recording never routes through the tracing
 * proxy (see recette/api/runners.py), so it produces zero proxy traces and can
 * never show up in the sessions view. Launching a recording here would be
 * misleading, so the launcher only drives a runtime agent through launchLaneB.
 *
 * Reuses the existing typed clients (listAgents / launchLaneB) -- no new client
 * function, no new endpoint.
 */

import { useEffect, useState } from "react";

import { launchLaneB, listAgents } from "../../api/client";
import type { AgentConfig } from "../../types/platform";

interface LaunchPanelProps {
  /** Called with the resulting run id once a launch resolves. */
  onLaunched: (runId: string) => void;
}

export default function LaunchPanel({ onLaunched }: LaunchPanelProps): JSX.Element {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);

  // Load the runtime agents on mount.
  useEffect(() => {
    let cancelled = false;
    listAgents()
      .then((list) => {
        if (!cancelled) {
          setAgents(list);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onLaunch = (): void => {
    if (selected === "" || busy) {
      return;
    }
    setBusy(true);
    setError("");
    launchLaneB({ agent_id: selected })
      .then((handle) => {
        onLaunched(handle.run_id);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className="proxy-subheader" data-testid="proxy-launch-panel">
      <label className="proxy-filter-label">
        Agent
        <select
          aria-label="agent"
          className="proxy-filter-input"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">--</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.id}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        className="proxy-export"
        data-testid="proxy-launch-btn"
        disabled={busy || selected === ""}
        onClick={onLaunch}
      >
        Lancer
      </button>

      {error !== "" && <span className="proxy-error">{error}</span>}
    </div>
  );
}
