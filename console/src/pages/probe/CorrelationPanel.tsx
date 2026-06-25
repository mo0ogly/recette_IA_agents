/**
 * CorrelationPanel -- the analyst's 2x2 quadrant view joining the static
 * discovery scan (source risk) with the runtime behavioral wave (measured risk).
 *
 * The headline research signal is `static_blind`: an agent the scanner called
 * clean that behaves dirty at runtime. The panel renders the four quadrants,
 * highlights static_blind in the alert accent, lists unresolved links and
 * coverage gaps fail-loud, and exposes a threshold knob that re-fetches via
 * POST /behavior/correlate.
 *
 * CorrelationPanel is presentational when `recording` is omitted (receive-only);
 * when `recording` is provided the threshold knob is enabled and triggers a
 * live re-fetch via correlateBehavior.
 *
 * CSS: quadrant grid tokens live in probe.css (no hardcoded colors here).
 */

import { useState, useEffect } from "react";
import {
  correlateBehavior,
  type CorrelationReport,
  type BehaviorProfile,
} from "../../api/client";

// ---------------------------------------------------------------------------
// Quadrant metadata
// ---------------------------------------------------------------------------

const QUADRANT_KEYS = [
  "agree_clean",
  "static_blind",
  "static_overflag",
  "agree_dirty",
] as const;

type QuadrantKey = (typeof QUADRANT_KEYS)[number];

const QUADRANT_LABEL: Record<QuadrantKey, string> = {
  agree_clean: "agree clean",
  static_blind: "static blind",
  static_overflag: "static overflag",
  agree_dirty: "agree dirty",
};

/** static_blind is the headline anomaly: source-clean, runtime-dirty. */
const QUADRANT_ALERT: Set<QuadrantKey> = new Set(["static_blind"]);

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function QuadrantCell({
  name,
  agentIds,
  count,
}: {
  name: QuadrantKey;
  agentIds: string[] | null;
  count: number | null;
}): JSX.Element {
  const isAlert = QUADRANT_ALERT.has(name);
  const cellClass = [
    "corr-quadrant",
    isAlert ? "corr-quadrant-alert" : "corr-quadrant-normal",
  ].join(" ");

  return (
    <div className={cellClass} data-testid={`quadrant-${name}`}>
      <h5 className="corr-quadrant-label">{QUADRANT_LABEL[name]}</h5>
      {agentIds !== null ? (
        agentIds.length === 0 ? (
          <span className="corr-quadrant-empty">none</span>
        ) : (
          <ul className="corr-quadrant-agents">
            {agentIds.map((id) => (
              <li key={id} className="corr-quadrant-agent-id">
                {id}
              </li>
            ))}
          </ul>
        )
      ) : (
        <span className="corr-quadrant-count">{count ?? 0}</span>
      )}
    </div>
  );
}

function UnresolvedBlock({
  unresolved,
}: {
  unresolved: CorrelationReport["unresolved"];
}): JSX.Element | null {
  if (unresolved.length === 0) return null;
  return (
    <div className="corr-unresolved" data-testid="corr-unresolved" role="alert">
      <span className="corr-unresolved-label">UNRESOLVED (fail-loud)</span>
      <ul className="corr-unresolved-list">
        {unresolved.map((u) => (
          <li key={u.agent_id}>
            <span className="corr-unresolved-id">{u.agent_id}</span>
            <span className="corr-unresolved-reason">{u.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CoverageGapBlock({
  gaps,
}: {
  gaps: CorrelationReport["coverage_gaps"];
}): JSX.Element | null {
  if (gaps.length === 0) return null;
  return (
    <div className="corr-gaps" data-testid="corr-coverage-gaps" role="alert">
      <span className="corr-gaps-label">COVERAGE GAPS</span>
      <span className="corr-gaps-list">
        {gaps.map((g) => g.discovery_subject).join(", ")}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CorrelationPanel({
  correlation: initialCorrelation,
  recording,
}: {
  /** Initial correlation data (R16: real fixture in the contract test). When
   *  omitted alongside `recording`, the component auto-fetches on mount. */
  correlation?: CorrelationReport | null;
  recording?: unknown;
}): JSX.Element | null {
  const [current, setCurrent] = useState<CorrelationReport | null>(
    initialCorrelation ?? null,
  );
  const [threshold, setThreshold] = useState<number>(
    initialCorrelation?.thresholds.runtime_dirty ?? 50,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canRun = recording !== undefined && recording !== null;

  // Auto-fetch on mount when recording is available but no initial data.
  useEffect(() => {
    if (canRun && current === null) {
      setBusy(true);
      correlateBehavior({ recording, thresholds: { runtime_dirty: threshold } })
        .then((r) => {
          setCurrent(r);
          setThreshold(r.thresholds.runtime_dirty);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setBusy(false));
    }
    // Only on mount / when recording first becomes available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canRun]);

  const run = async () => {
    if (!canRun) return;
    setBusy(true);
    setError(null);
    const profile: BehaviorProfile = { threat: "exfil" };
    try {
      const result = await correlateBehavior({
        recording,
        profile,
        thresholds: { runtime_dirty: threshold },
      });
      setCurrent(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="corr-panel" data-testid="corr-panel">
      <h4 className="corr-title">
        Behavior &lt;-&gt; Discovery correlation -- source risk vs runtime risk
      </h4>

      {current && (
        <div className="corr-provenance" data-testid="corr-provenance">
          <span className="corr-prov-version">{current.tool_version}</span>
          <span className="corr-prov-sep">&middot;</span>
          <span className="corr-prov-threshold">
            runtime_dirty threshold: {current.thresholds.runtime_dirty}
          </span>
        </div>
      )}

      {canRun && (
        <div className="corr-controls">
          <label className="corr-knob">
            runtime_dirty threshold
            <input
              type="number"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              data-testid="corr-threshold-input"
            />
          </label>
          <button
            type="button"
            className="probe-button"
            onClick={run}
            disabled={busy}
            data-testid="corr-run-button"
          >
            {busy ? "running..." : "Re-correlate"}
          </button>
        </div>
      )}

      {error && (
        <div className="corr-error probe-error" role="alert">
          {error}
        </div>
      )}

      {busy && !current && (
        <p className="corr-loading probe-note">Running correlation...</p>
      )}

      {current && (
        <>
          <div className="corr-grid" data-testid="corr-grid">
            <QuadrantCell
              name="agree_clean"
              agentIds={null}
              count={current.quadrants.agree_clean}
            />
            <QuadrantCell
              name="static_blind"
              agentIds={current.quadrants.static_blind}
              count={null}
            />
            <QuadrantCell
              name="static_overflag"
              agentIds={current.quadrants.static_overflag}
              count={null}
            />
            <QuadrantCell
              name="agree_dirty"
              agentIds={null}
              count={current.quadrants.agree_dirty}
            />
          </div>

          <UnresolvedBlock unresolved={current.unresolved} />
          <CoverageGapBlock gaps={current.coverage_gaps} />
        </>
      )}
    </section>
  );
}
