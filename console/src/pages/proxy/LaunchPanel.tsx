/**
 * Mini-launcher for the proxy page.
 *
 * One screen to "launch and watch it in the proxy": pick a runtime agent OR a
 * recording, launch it, and let the page auto-switch to the sessions source
 * preselected on that run (SessionsPanel reads ?run=). The panel owns only its
 * local selection state; it reports the resulting run id through onLaunched and
 * lets the parent page own the URL (it sets ?source=sessions&run=<run_id>).
 *
 * Reuses the existing typed clients (listAgents / launchLaneB / listRecordings /
 * replayRecording) -- no new client function, no new endpoint.
 */

import { useEffect, useState } from "react";

import { launchLaneB, listAgents, listRecordings, replayRecording } from "../../api/client";
import type { AgentConfig, RecordingMeta } from "../../types/platform";

/** Which kind of subject the launcher targets. */
type LaunchMode = "agent" | "recording";

interface LaunchPanelProps {
  /** Called with the resulting run id once a launch resolves. */
  onLaunched: (runId: string) => void;
}

export default function LaunchPanel({ onLaunched }: LaunchPanelProps): JSX.Element {
  const [mode, setMode] = useState<LaunchMode>("agent");
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [recordings, setRecordings] = useState<RecordingMeta[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);

  // Load the relevant list on mount and whenever the mode changes. Selection is
  // reset so a stale id from the other mode can never be launched.
  useEffect(() => {
    let cancelled = false;
    setSelected("");
    setError("");
    const load =
      mode === "agent"
        ? listAgents().then((list) => {
            if (!cancelled) {
              setAgents(list);
            }
          })
        : listRecordings().then((list) => {
            if (!cancelled) {
              setRecordings(list);
            }
          });
    load.catch((err: unknown) => {
      if (!cancelled) {
        setError(err instanceof Error ? err.message : String(err));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [mode]);

  const onLaunch = (): void => {
    if (selected === "" || busy) {
      return;
    }
    setBusy(true);
    setError("");
    const launch =
      mode === "agent"
        ? launchLaneB({ agent_id: selected })
        : replayRecording(selected);
    launch
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
        Lancer
        <select
          aria-label="source"
          className="proxy-filter-input"
          value={mode}
          onChange={(e) => setMode(e.target.value as LaunchMode)}
        >
          <option value="agent">agent</option>
          <option value="recording">recording</option>
        </select>
      </label>

      <label className="proxy-filter-label">
        {mode === "agent" ? "Agent" : "Recording"}
        <select
          aria-label={mode}
          className="proxy-filter-input"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">--</option>
          {mode === "agent"
            ? agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.id}
                </option>
              ))
            : recordings.map((r) => (
                <option key={r.recording_id} value={r.recording_id}>
                  {r.recording_id}
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
