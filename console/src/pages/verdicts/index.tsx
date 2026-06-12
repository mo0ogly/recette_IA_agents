/**
 * Verdicts page: judged submissions of external discovery/identification
 * tools against the agents' stored ground truth.
 *
 * Shows the scorecard aggregates (GET /verdicts/scorecard), the per-agent
 * judged table of the latest submission (GET /verdicts), and offers two
 * submission paths: an HTTP hint (curl against POST /verdicts) and a JSON
 * file upload parsed client-side then submitted via the typed client.
 *
 * Contract notes (R16, captured against the real backend):
 * - GET /verdicts and /verdicts/scorecard answer 404 before any submission;
 *   the client maps that to null and this page renders the empty state.
 * - checks/expected/observed/evidence_event_ids are absent on SKIP and
 *   unknown-agent FAIL entries (only the error field is set on the latter).
 * - Evidence event ids deep-link to /audit?event_id=<id>; the audit page
 *   reads that param and shows an active-filter chip for the single event.
 */

import { Fragment, useCallback, useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { Link } from "react-router-dom";

import { getVerdictScorecard, getVerdicts, postVerdicts } from "../../api/client";
import type {
  JudgedEntry,
  JudgedStatus,
  VerdictDimension,
  VerdictScorecard,
  VerdictSubmission,
  VerdictSubmissionRequest,
} from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import { auditEventToLogLine, LogConsole } from "../../components/LogConsole";
import { useAuditTail } from "../../hooks/useAuditTail";
import "./verdicts.css";

const DIMENSIONS: readonly VerdictDimension[] = [
  "identity",
  "capabilities",
  "policy",
  "behavior",
];

const CURL_HINT =
  'curl -X POST $AGENTRAIL_API_URL/verdicts -H "Content-Type: application/json" -d \'{"tool": "my-tool", "results": [{"agent_id": "...", "detected": true}]}\'';

/** Render a [0, 1] fraction as a percentage, or n/a when nothing was checked. */
function ratePercent(rate: number | null): string {
  if (rate === null) {
    return "n/a";
  }
  return `${Math.round(rate * 100)}%`;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Split the checks map of a judged entry into failed and passed check names. */
function splitChecks(entry: JudgedEntry): { failed: string[]; passed: string[] } {
  const failed: string[] = [];
  const passed: string[] = [];
  for (const [name, ok] of Object.entries(entry.checks ?? {})) {
    (ok ? passed : failed).push(name);
  }
  return { failed, passed };
}

/**
 * Validate the parsed upload client-side before submitting: the backend
 * expects { tool, results: [...] } and would 400 on anything else.
 */
function parseSubmission(text: string): VerdictSubmissionRequest {
  const parsed: unknown = JSON.parse(text);
  if (
    parsed === null ||
    typeof parsed !== "object" ||
    typeof (parsed as { tool?: unknown }).tool !== "string" ||
    !Array.isArray((parsed as { results?: unknown }).results)
  ) {
    throw new Error('Invalid verdict file: expected {"tool": "...", "results": [...]}');
  }
  return parsed as unknown as VerdictSubmissionRequest;
}

/** FileReader-based read (jsdom-safe, unlike Blob.text in some environments). */
function readFileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("file read failed"));
    reader.readAsText(file);
  });
}

function StatusChip({ status }: { status: JudgedStatus }): JSX.Element {
  return (
    <span className="verdict-chip" data-status={status}>
      {status}
    </span>
  );
}

function ScorecardBanner({ card }: { card: VerdictScorecard }): JSX.Element {
  return (
    <div className="verdict-scorecard" data-testid="verdict-scorecard">
      <div className="verdict-scorecard-group">
        <span className="verdict-stat" data-testid="scorecard-total">
          <span className="verdict-stat-label">Total</span> {card.total}
        </span>
        <span className="verdict-stat" data-testid="scorecard-passed">
          <span className="verdict-stat-label">Passed</span> {card.passed}
        </span>
        <span className="verdict-stat" data-testid="scorecard-skipped">
          <span className="verdict-stat-label">Skipped</span> {card.skipped}
        </span>
        <span className="verdict-stat" data-testid="scorecard-detection">
          <span className="verdict-stat-label">Detection rate</span>{" "}
          {ratePercent(card.detection_rate)}
        </span>
      </div>
      <div className="verdict-scorecard-group">
        {DIMENSIONS.map((dim) => (
          <span
            key={dim}
            className="verdict-stat"
            data-testid={`scorecard-dim-${dim}`}
          >
            <span className="verdict-stat-label">{dim}</span>{" "}
            {ratePercent(card.accuracy_by_dimension[dim])}
          </span>
        ))}
      </div>
      <div className="verdict-scorecard-group">
        <span className="verdict-stat" data-testid="scorecard-fp">
          <span className="verdict-stat-label">False positives</span>{" "}
          {card.false_positives}
        </span>
        <span className="verdict-stat" data-testid="scorecard-fn">
          <span className="verdict-stat-label">False negatives</span>{" "}
          {card.false_negatives}
        </span>
      </div>
    </div>
  );
}

function JudgedDetail({ entry, rowKey }: { entry: JudgedEntry; rowKey: string }): JSX.Element {
  const { failed, passed } = splitChecks(entry);
  const evidence = entry.evidence_event_ids ?? [];
  return (
    <div className="verdict-detail" data-testid={`verdict-detail-${rowKey}`}>
      <div className="verdict-detail-checks">
        <div data-testid="failed-checks">
          <h4>Failed checks</h4>
          {failed.length === 0 ? (
            <p className="verdict-detail-empty">none</p>
          ) : (
            <ul>
              {failed.map((name) => (
                <li key={name} className="verdict-check-failed">
                  {name}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div data-testid="passed-checks">
          <h4>Passed checks</h4>
          {passed.length === 0 ? (
            <p className="verdict-detail-empty">none</p>
          ) : (
            <ul>
              {passed.map((name) => (
                <li key={name} className="verdict-check-passed">
                  {name}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="verdict-detail-json">
        <div>
          <h4>Expected (ground truth)</h4>
          <pre data-testid="expected-json">
            {JSON.stringify(entry.expected ?? null, null, 2)}
          </pre>
        </div>
        <div>
          <h4>Observed (tool result)</h4>
          <pre data-testid="observed-json">
            {JSON.stringify(entry.observed ?? null, null, 2)}
          </pre>
        </div>
      </div>
      <div className="verdict-detail-evidence">
        <h4>Evidence events</h4>
        {evidence.length === 0 ? (
          <p className="verdict-detail-empty">no audit events for this agent</p>
        ) : (
          <ul>
            {evidence.map((eventId) => (
              <li key={eventId}>
                {/* Deep-link to the audit page filtered on this event id; the
                    audit page reads ?event_id= and shows an active-filter chip. */}
                <Link
                  to={`/audit?event_id=${encodeURIComponent(eventId)}`}
                  className="verdict-evidence-link mono"
                >
                  {eventId}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function VerdictsPage(): JSX.Element {
  const [latest, setLatest] = useState<VerdictSubmission | null>(null);
  const [card, setCard] = useState<VerdictScorecard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const audit = useAuditTail();

  const refresh = useCallback(async (): Promise<void> => {
    try {
      // Both calls map an expected 404 (no submission yet) to null.
      const [latestResult, cardResult] = await Promise.all([
        getVerdicts(),
        getVerdictScorecard(),
      ]);
      setLatest(latestResult);
      setCard(cardResult);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    // Allow re-uploading the same file name later.
    event.target.value = "";
    if (file === undefined) {
      return;
    }
    try {
      const payload = parseSubmission(await readFileText(file));
      await postVerdicts(payload);
      setUploadError(null);
      await refresh();
    } catch (err) {
      setUploadError(errorMessage(err));
    }
  }

  /** Stable key of one judged row (agent_id can be null on malformed entries). */
  function rowKeyOf(entry: JudgedEntry, index: number): string {
    return entry.agent_id ?? `entry-${index}`;
  }

  return (
    <section>
      <div className="page-head">
        <h1>Verdicts</h1>
        <PageHelp topic="verdicts" />
      </div>

      {error !== null && (
        <div className="verdict-error-banner" role="alert">
          {error}
        </div>
      )}

      {card !== null && <ScorecardBanner card={card} />}

      {!loading && latest === null && error === null && (
        <div className="verdict-empty">
          <p className="verdict-empty-title">No verdict submission yet</p>
          <p>Two ways for a discovery/identification tool to submit results:</p>
          <ol>
            <li>
              HTTP, from the tool itself:
              <pre className="verdict-curl mono" data-testid="curl-hint">
                {CURL_HINT}
              </pre>
            </li>
            <li>Upload a results JSON file below.</li>
          </ol>
        </div>
      )}

      <div className="verdict-upload">
        <label htmlFor="verdict-upload-input">Upload results (.json)</label>
        <input
          id="verdict-upload-input"
          type="file"
          accept=".json"
          onChange={(e) => void handleUpload(e)}
        />
        {uploadError !== null && (
          <span className="verdict-upload-error" role="alert">
            {uploadError}
          </span>
        )}
      </div>

      {latest !== null && (
        <>
          <h2 className="verdict-table-title">
            Latest submission{latest.tool !== null ? ` — ${latest.tool}` : ""}{" "}
            <span className="verdict-subtle">(seq {latest.submitted_seq})</span>
          </h2>
          <table className="verdict-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Status</th>
                <th>Checks</th>
                <th>Evidence</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {latest.judged.map((entry, index) => {
                const rowKey = rowKeyOf(entry, index);
                const expanded = expandedRow === rowKey;
                const { failed } = splitChecks(entry);
                const checkCount = Object.keys(entry.checks ?? {}).length;
                return (
                  <Fragment key={rowKey}>
                    <tr
                      className="verdict-row"
                      onClick={() => setExpandedRow(expanded ? null : rowKey)}
                    >
                      <td>{entry.agent_id ?? "(no agent_id)"}</td>
                      <td>
                        <StatusChip status={entry.status} />
                      </td>
                      <td>
                        {checkCount > 0
                          ? `${checkCount - failed.length}/${checkCount} ok`
                          : "-"}
                      </td>
                      <td>{(entry.evidence_event_ids ?? []).length}</td>
                      <td>{entry.error ?? "-"}</td>
                    </tr>
                    {expanded && (
                      <tr className="verdict-detail-row">
                        <td colSpan={5}>
                          <JudgedDetail entry={entry} rowKey={rowKey} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      <div className="verdict-log">
        <LogConsole
          title="Audit log (live)"
          lines={audit.events.map(auditEventToLogLine)}
          onClear={audit.clear}
          stalled={audit.stalled}
          droppedCount={audit.droppedCount}
        />
      </div>
    </section>
  );
}
