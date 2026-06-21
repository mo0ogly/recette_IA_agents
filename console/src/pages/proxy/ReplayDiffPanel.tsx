/**
 * ReplayDiffPanel -- the "replay-diff" source of the Proxy console.
 *
 * Replay-determinism (I4) is the regression signal an expert reads here: a
 * recording replays as a pure function of its captured stream, so two replays of
 * the SAME recording MUST produce the SAME action sequence. This panel replays a
 * selected recording twice ("replay A" / "replay B"), distils each run into a
 * stable per-action summary (`runActionSummary`), and shows the line-aligned
 * `lineDiff` of the two. All rows `same` => "identique (I4)" (determinism holds);
 * any `left`/`right` row is a regression to investigate.
 *
 * Read-only over an effect that already happened (I1/I5): replaying a recording
 * re-derives its action-log, it never mutates a recorded side effect. Graceful:
 * any error surfaces as an inline line, never a crash. The two replays are the
 * honest, deterministic v1 of "original vs replay" -- it needs no extra
 * original-run plumbing and directly proves the I4 property.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getRunEvents,
  listRecordings,
  replayRecording,
} from "../../api/client";
import type { RecordingMeta, RunEvent } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";
import { lineDiff } from "./diff";
import { runActionSummary } from "./replayDiff";

/** A replayed run is terminal once it carries a result/end/error frame. */
function isTerminal(events: readonly RunEvent[]): boolean {
  return events.some(
    (e) => e.type === "result" || e.type === "end" || e.type === "error",
  );
}

const POLL_TRIES = 20;
const POLL_INTERVAL_MS = 250;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Replay the recording, then poll its events until terminal (or tries cap),
 *  and return the stable action summary of the resulting run. */
async function replayAndSummarize(recordingId: string): Promise<string> {
  const handle = await replayRecording(recordingId);
  let events: RunEvent[] = [];
  for (let i = 0; i < POLL_TRIES; i++) {
    events = await getRunEvents(handle.run_id);
    if (isTerminal(events)) {
      break;
    }
    if (i < POLL_TRIES - 1) {
      await sleep(POLL_INTERVAL_MS);
    }
  }
  return runActionSummary(events);
}

export default function ReplayDiffPanel({ onStatus }: SourcePanelProps): JSX.Element {
  const [recordings, setRecordings] = useState<RecordingMeta[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [summaryA, setSummaryA] = useState<string | null>(null);
  const [summaryB, setSummaryB] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onStatusRef = useRef(onStatus);
  useEffect(() => {
    onStatusRef.current = onStatus;
  }, [onStatus]);

  useEffect(() => {
    let alive = true;
    listRecordings()
      .then((recs) => {
        if (!alive) {
          return;
        }
        setRecordings(recs);
        if (recs.length > 0) {
          setSelectedId((cur) => (cur === "" ? recs[0].recording_id : cur));
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          setError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  const rows =
    summaryA !== null && summaryB !== null ? lineDiff(summaryA, summaryB) : null;
  const identical = rows !== null && rows.every((r) => r.kind === "same");

  useEffect(() => {
    onStatusRef.current?.({
      count: rows === null ? 0 : rows.length,
      failed: rows === null ? 0 : rows.filter((r) => r.kind !== "same").length,
    });
  }, [rows]);

  const onReplay = useCallback(async (): Promise<void> => {
    if (selectedId === "") {
      return;
    }
    setBusy(true);
    setError(null);
    setSummaryA(null);
    setSummaryB(null);
    try {
      const a = await replayAndSummarize(selectedId);
      const b = await replayAndSummarize(selectedId);
      setSummaryA(a);
      setSummaryB(b);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [selectedId]);

  return (
    <section className="proxy-app" data-testid="replay-diff-panel">
      <div className="proxy-subheader">
        <label className="proxy-filter-label">
          recording
          <select
            className="proxy-filter-input"
            data-testid="replay-diff-select"
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {recordings.length === 0 && <option value="">aucun recording</option>}
            {recordings.map((r) => (
              <option key={r.recording_id} value={r.recording_id}>
                {r.recording_id}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="proxy-export"
          data-testid="replay-diff-run"
          disabled={busy || selectedId === ""}
          onClick={() => void onReplay()}
        >
          {busy ? "Replay en cours..." : "Rejouer + diff"}
        </button>
      </div>

      {error !== null && <p className="proxy-error">{error}</p>}

      {rows !== null && (
        <div className="proxy-wire-diff" data-testid="replay-diff">
          <div className="proxy-wire-diff-head">
            <span>replay A vs replay B</span>
            {identical ? (
              <span
                className="proxy-badge"
                data-outcome="ok"
                data-testid="replay-diff-identical"
              >
                identique (I4)
              </span>
            ) : (
              <span
                className="proxy-badge"
                data-outcome="fail"
                data-testid="replay-diff-regression"
              >
                regression
              </span>
            )}
          </div>
          <table className="proxy-wire-diff-table">
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="proxy-wire-diff-row" data-kind={row.kind}>
                  <td className="proxy-wire-diff-cell" data-side="left">
                    {row.left}
                  </td>
                  <td className="proxy-wire-diff-cell" data-side="right">
                    {row.right}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
