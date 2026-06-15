/**
 * Red-team panel.
 *
 * A real adversarial-recette cockpit, legibility-first (CLAUDE.md): for each
 * red-team subject it surfaces what the recette DECIDED (the four-dimension
 * verdict + caught/missed), what the adversary DID (the Crescendo escalation
 * transcript / the goal) and what the subject actually DID (the ordered action
 * log, with the out-of-scope / unapproved action flagged).
 *
 * Two families behind one shape: MAF subjects (tool/handoff, GET /sim/scenarios)
 * and Git agents (Lane B, GET /sim/git-scenarios). Each renders a responsive
 * grid of scenario cards; selecting one opens a detail panel (one at a time).
 * A caught anomaly (verdict=incorrect, single-axis) can be promoted to a frozen
 * negative corpus subject (POST /sim/scenarios/{id}/promote).
 *
 * The frozen-recordings stepper (GET /sim/runs) is kept as a secondary section.
 * Everything here is RECORDED and deterministic (I4) -- no live LLM is triggered.
 */

import { useEffect, useMemo, useState } from "react";
import {
  getSimGitScenario,
  getSimGitScenarios,
  getSimRuns,
  getSimScenario,
  getSimScenarios,
  getSimView,
  promoteSimScenario,
} from "../../api/client";
import type {
  SimPromoteResult,
  SimRunSummary,
  SimScenario,
  SimScenarioView,
  SimView,
} from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import "./sim.css";

const DIMS = ["identity", "capabilities", "policy", "behavior"] as const;
type DimName = (typeof DIMS)[number];

/** Standards keys surfaced as chips, in display order. */
const TAG_KEYS = ["owasp_asi", "mitre_atlas", "nist"] as const;

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** A small string field read defensively from a free-form action-log row. */
function actionField(row: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
    if (typeof value === "number") {
      return String(value);
    }
  }
  return undefined;
}

// ---------------------------------------------------------------------------
// Scenario card grid (pure, exported for testability)
// ---------------------------------------------------------------------------

/**
 * Pure presentational grid of red-team scenario cards. Each card shows the
 * subject name, its family + strategy (violation_type) chip, a prominent
 * caught/missed badge (green/red), the predicted-vs-expected verdict, the
 * OWASP/ATLAS/NIST standards chips, and a "Promote to corpus" button enabled
 * only for a caught anomaly (verdict=incorrect). The card is clickable to open
 * the detail panel via onSelect; promote state is kept locally per scenario id.
 *
 * Kept pure (no fetch except the explicit promote action) so it renders from a
 * captured fixture under test (R16).
 */
export function ScenarioList({
  scenarios,
  selected,
  onSelect,
}: {
  scenarios: SimScenario[];
  selected?: string | null;
  onSelect?: (id: string) => void;
}): JSX.Element {
  const [promoted, setPromoted] = useState<Record<string, SimPromoteResult>>({});
  const [promoteError, setPromoteError] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});

  const onPromote = (id: string): void => {
    setPending((p) => ({ ...p, [id]: true }));
    setPromoteError((e) => {
      const next = { ...e };
      delete next[id];
      return next;
    });
    promoteSimScenario(id)
      .then((res) => setPromoted((p) => ({ ...p, [id]: res })))
      .catch((err) => setPromoteError((e) => ({ ...e, [id]: errorMessage(err) })))
      .finally(() => setPending((p) => ({ ...p, [id]: false })));
  };

  if (scenarios.length === 0)
    return (
      <p className="sim-empty" data-testid="sim-scn-empty">
        No red-team scenarios.
      </p>
    );

  return (
    <ul className="sim-grid" data-testid="sim-scenarios">
      {scenarios.map((s) => {
        const caughtAnomaly = s.verdict === "incorrect";
        const result = promoted[s.scenario_id];
        const error = promoteError[s.scenario_id];
        return (
          <li key={s.scenario_id} data-testid={`sim-scn-${s.scenario_id}`}>
            <button
              type="button"
              className="sim-card"
              data-testid={`sim-scn-card-${s.scenario_id}`}
              data-selected={selected === s.scenario_id ? "true" : "false"}
              onClick={() => onSelect?.(s.scenario_id)}
            >
              <div className="sim-card-top">
                <span
                  className={`sim-chip ${s.anomaly_caught ? "sim-caught" : "sim-missed"}`}
                  data-testid={`sim-scn-caught-${s.scenario_id}`}
                >
                  {s.anomaly_caught ? "caught" : "missed"}
                </span>
                {s.family && <span className="sim-chip sim-chip-neutral">{s.family}</span>}
                {s.violation_type && (
                  <span className="sim-chip sim-chip-accent">{s.violation_type}</span>
                )}
              </div>
              <span className="sim-card-title">{s.name}</span>
              <span className="sim-verdict-line">
                predicted <strong>{s.verdict}</strong> · expected{" "}
                <strong>{s.expected_verdict}</strong>
              </span>
              <div className="sim-card-tags">
                {TAG_KEYS.map((key) =>
                  s.tags[key] ? (
                    <span
                      key={key}
                      className="sim-chip sim-chip-neutral"
                      data-testid={
                        key === "owasp_asi" ? `sim-scn-owasp-${s.scenario_id}` : undefined
                      }
                    >
                      {s.tags[key]}
                    </span>
                  ) : null,
                )}
              </div>
            </button>
            <div className="sim-card-foot">
              <button
                type="button"
                className="pill"
                data-testid={`sim-scn-promote-${s.scenario_id}`}
                disabled={
                  !caughtAnomaly || pending[s.scenario_id] || result !== undefined
                }
                title={caughtAnomaly ? undefined : "nothing to promote"}
                onClick={() => onPromote(s.scenario_id)}
              >
                {result ? "Promoted" : "Promote to corpus"}
              </button>
            </div>
            {result && (
              <ul className="sim-promoted" data-testid={`sim-scn-promoted-${s.scenario_id}`}>
                {result.created.map((path) => (
                  <li key={path}>
                    <code>{path}</code>
                  </li>
                ))}
              </ul>
            )}
            {error && (
              <span
                className="sim-promote-error"
                role="alert"
                data-testid={`sim-scn-promote-error-${s.scenario_id}`}
              >
                {error}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Scenario detail panel (pure, exported for testability)
// ---------------------------------------------------------------------------

function DimensionMatrix({
  scenarioId,
  dimensions,
}: {
  scenarioId: string;
  dimensions: SimScenarioView["dimensions"];
}): JSX.Element {
  return (
    <div className="sim-detail-block">
      <h4>Four-dimension verdict</h4>
      <div className="sim-dims">
        {DIMS.map((d) => {
          const conform = dimensions[d as DimName];
          return (
            <span
              key={d}
              className="sim-dim"
              data-state={conform ? "conform" : "broken"}
              data-testid={`sim-scn-dim-${scenarioId}-${d}`}
            >
              <span className="sim-dim-mark">{conform ? "OK" : "X"}</span> {d}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Pure detail view of one scenario: the four-dimension matrix (the broken axis
 * is the anomaly), the adversarial timeline (MAF transcript -- the Crescendo
 * escalation -- or the git goal) and the ordered action log with the
 * out-of-scope / unapproved action flagged. Rendered from a captured fixture
 * under test (R16).
 */
export function ScenarioDetail({ view }: { view: SimScenarioView }): JSX.Element {
  const transcript = view.transcript ?? [];
  const actions = view.action_log ?? [];
  return (
    <section className="sim-detail" data-testid={`sim-scn-detail-${view.scenario_id}`}>
      <div className="sim-detail-head">
        <h3>{view.name}</h3>
        <span
          className={`sim-chip ${view.anomaly_caught ? "sim-caught" : "sim-missed"}`}
        >
          {view.anomaly_caught ? "caught" : "missed"}
        </span>
      </div>
      {view.goal && <p className="sim-detail-goal">Goal: {view.goal}</p>}

      <DimensionMatrix scenarioId={view.scenario_id} dimensions={view.dimensions} />

      {transcript.length > 0 && (
        <div className="sim-detail-block">
          <h4>Attack timeline (Crescendo escalation)</h4>
          <ol className="sim-timeline" data-testid={`sim-scn-transcript-${view.scenario_id}`}>
            {transcript.map((t, i) => (
              <li className="sim-turn" data-role={t.role} key={i}>
                <span className="sim-turn-role">{t.role}</span>
                <span className="sim-turn-body">
                  {t.content ? (
                    t.content
                  ) : (
                    <span className="sim-turn-empty">(tool call)</span>
                  )}
                  {t.tool_name && <code className="sim-turn-tool">{t.tool_name}</code>}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {actions.length > 0 && (
        <div className="sim-detail-block">
          <h4>Action log</h4>
          <ul className="sim-actions" data-testid={`sim-scn-actions-${view.scenario_id}`}>
            {actions.map((row, i) => {
              const seq = actionField(row, "seq");
              const name = actionField(row, "action_type", "action") ?? "action";
              const target =
                actionField(row, "target", "resource", "target_system") ?? "";
              const mode = actionField(row, "mode", "tool_kind");
              // The unapproved action is the anomaly the subject was coerced into.
              const flagged = row.approved === false;
              return (
                <li className="sim-action" data-flagged={flagged ? "true" : "false"} key={i}>
                  <span className="sim-action-seq">{seq ?? i}</span>
                  <span className="sim-action-name">{name}</span>
                  {target && <span className="sim-action-target">{target}</span>}
                  {mode && <span className="sim-action-meta">{mode}</span>}
                  {flagged && (
                    <span className="sim-chip sim-missed sim-action-flag">unapproved</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// One family section: grid + on-demand detail
// ---------------------------------------------------------------------------

function FamilySection({
  title,
  subtitle,
  scenarios,
  fetchDetail,
}: {
  title: string;
  subtitle: string;
  scenarios: SimScenario[];
  fetchDetail: (id: string) => Promise<SimScenarioView>;
}): JSX.Element {
  const [open, setOpen] = useState<string | null>(null);
  const [view, setView] = useState<SimScenarioView | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (open === null) {
      setView(null);
      return;
    }
    let alive = true;
    setView(null);
    setDetailError(null);
    fetchDetail(open)
      .then((v) => alive && setView(v))
      .catch((e) => alive && setDetailError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, [open, fetchDetail]);

  const onSelect = (id: string): void => setOpen((cur) => (cur === id ? null : id));

  return (
    <section>
      <div className="sim-section-head">
        <h2>{title}</h2>
        <span className="sim-section-sub">{subtitle}</span>
      </div>
      <ScenarioList scenarios={scenarios} selected={open} onSelect={onSelect} />
      {detailError && (
        <div className="sim-error" role="alert">
          {detailError}
        </div>
      )}
      {view && <ScenarioDetail view={view} />}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Frozen-recordings stepper (secondary section, unchanged behaviour)
// ---------------------------------------------------------------------------

function Viewer({ agentId }: { agentId: string }): JSX.Element {
  const [view, setView] = useState<SimView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    let alive = true;
    setView(null);
    setError(null);
    setCursor(0);
    getSimView(agentId)
      .then((v) => alive && setView(v))
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, [agentId]);

  if (error)
    return (
      <div className="sim-error" role="alert" data-testid="sim-error">
        {error}
      </div>
    );
  if (!view) return <p className="sim-loading">Loading run...</p>;
  const last = view.turns.length - 1;

  return (
    <section data-testid="sim-view">
      <div className="sim-section-head">
        <h2>{view.name}</h2>
      </div>
      <div className="sim-dims">
        <span
          className={`sim-chip ${view.verdict === "correct" ? "sim-caught" : "sim-missed"}`}
          data-testid="sim-verdict"
        >
          {view.verdict}
        </span>
        <span className="sim-section-sub" data-testid="sim-stopped">
          {view.stopped_reason}
        </span>
        {DIMS.map((d) => (
          <span
            key={d}
            className="sim-dim"
            data-state={view.dimensions[d] ? "conform" : "broken"}
            data-testid={`sim-dim-${d}`}
          >
            {d}
          </span>
        ))}
      </div>

      <div className="sim-card-foot">
        <button
          type="button"
          className="pill"
          disabled={cursor <= 0}
          onClick={() => setCursor((c) => Math.max(0, c - 1))}
        >
          Prev
        </button>
        <span className="sim-section-sub" data-testid="sim-cursor">
          turn {view.turns.length ? cursor + 1 : 0}/{view.turns.length}
        </span>
        <button
          type="button"
          className="pill"
          disabled={cursor >= last}
          onClick={() => setCursor((c) => Math.min(last, c + 1))}
        >
          Next
        </button>
      </div>

      <ol className="sim-timeline">
        {view.turns.map((t) => (
          <li
            className="sim-turn"
            data-role={t.role}
            key={t.index}
            data-testid={`sim-turn-${t.index}`}
            data-current={t.index === cursor ? "true" : undefined}
          >
            <span className="sim-turn-role">{t.role}</span>
            <span className="sim-turn-body">{t.content}</span>
          </li>
        ))}
      </ol>

      {view.checks.length > 0 && (
        <ul className="sim-actions" data-testid="sim-checks">
          {view.checks.map((c, i) => (
            <li className="sim-action" data-flagged={c.passed ? "false" : "true"} key={i}>
              <span className="sim-action-name">{c.passed ? "PASS" : "FAIL"}</span>{" "}
              <span className="sim-action-meta">{c.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SimPage(): JSX.Element {
  const [mafScenarios, setMafScenarios] = useState<SimScenario[] | null>(null);
  const [mafError, setMafError] = useState<string | null>(null);
  const [gitScenarios, setGitScenarios] = useState<SimScenario[] | null>(null);
  const [gitError, setGitError] = useState<string | null>(null);

  const [runs, setRuns] = useState<SimRunSummary[] | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [openRun, setOpenRun] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getSimScenarios()
      .then((r) => alive && setMafScenarios(r.scenarios))
      .catch((e) => alive && setMafError(errorMessage(e)));
    getSimGitScenarios()
      .then((r) => alive && setGitScenarios(r.scenarios))
      .catch((e) => alive && setGitError(errorMessage(e)));
    getSimRuns()
      .then((r) => {
        if (alive) {
          setRuns(r.runs);
          setOpenRun(r.runs[0]?.agent_id ?? null);
        }
      })
      .catch((e) => alive && setRunError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, []);

  const runBody = useMemo(() => openRun && <Viewer agentId={openRun} />, [openRun]);

  return (
    <section className="sim-page">
      <div className="page-head">
        <h1>Red-team panel</h1>
        <PageHelp topic="corpus" />
      </div>
      <p className="sim-intro">
        Adversarial recette, legibility-first: for each subject, what the recette
        DECIDED (four-dimension verdict, caught/missed), what the adversary DID
        (the Crescendo escalation) and what the subject actually DID (the action
        log, with the out-of-scope action flagged). Recorded and deterministic --
        no live LLM is triggered here. A caught single-axis anomaly can be frozen
        into a negative corpus subject.
      </p>

      {/* MAF subjects */}
      {mafError && (
        <div className="sim-error" role="alert" data-testid="sim-scenarios-error">
          {mafError}
        </div>
      )}
      {!mafScenarios && !mafError && <p className="sim-loading">Loading MAF subjects...</p>}
      {mafScenarios && (
        <FamilySection
          title="MAF subjects"
          subtitle="Tool / handoff agents driven through adversarial turns"
          scenarios={mafScenarios}
          fetchDetail={getSimScenario}
        />
      )}

      {/* Git agents (Lane B) */}
      {gitError && (
        <div className="sim-error" role="alert" data-testid="sim-git-scenarios-error">
          {gitError}
        </div>
      )}
      {!gitScenarios && !gitError && <p className="sim-loading">Loading git agents...</p>}
      {gitScenarios && (
        <FamilySection
          title="Git agents (Lane B)"
          subtitle="GitHub / GitLab agents coerced beyond their declared scope"
          scenarios={gitScenarios}
          fetchDetail={getSimGitScenario}
        />
      )}

      {/* Frozen recordings (secondary) */}
      <section className="sim-recordings">
        <div className="sim-section-head">
          <h2>Frozen recordings</h2>
          <span className="sim-section-sub">
            Step through a recorded deterministic conversation
          </span>
        </div>
        {runError && (
          <div className="sim-error" role="alert" data-testid="sim-list-error">
            {runError}
          </div>
        )}
        {!runs && !runError && <p className="sim-loading">Loading runs...</p>}
        {runs && (
          <div className="sim-card-tags">
            {runs.map((r) => (
              <button
                key={r.agent_id}
                type="button"
                className={`pill ${openRun === r.agent_id ? "sim-caught" : ""}`}
                data-testid={`sim-run-${r.agent_id}`}
                onClick={() => setOpenRun(r.agent_id)}
              >
                {r.name} · {r.verdict}
              </button>
            ))}
          </div>
        )}
        {runBody}
      </section>
    </section>
  );
}
