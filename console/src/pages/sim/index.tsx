/**
 * Red-team panel.
 *
 * PURPOSE (legibility-first, CLAUDE.md): this screen proves whether the
 * IDENTIFICATION tool catches a red-team anomaly. Each scenario drives an agent
 * under an adversarial escalation; the recette then checks that the EXPECTED
 * verdict is the one rendered -- either the anomaly was caught (true positive),
 * or the conform agent raised no false alarm (true negative).
 *
 * The page is organised in TABS (one subject per tab), mirroring the CLI:
 *  - "Scorecard": the client-side mirror of `recette redteam` (total / caught /
 *    missed, by OWASP) computed from the MAF + git scenario lists.
 *  - "Sujets MAF": MAF tool/handoff scenario cards + detail.
 *  - "Agents Git (Lane B)": git scenario cards + detail.
 *  - "Enregistrements figes": the frozen-recordings stepper.
 *
 * Everything here is RECORDED and deterministic (I4) -- no live LLM is triggered.
 * A caught single-axis anomaly can be promoted to a frozen negative corpus
 * subject (the CLI promote, mirrored by the "Promouvoir vers le corpus" button).
 * Live recording (`recette redteam-record`, which needs provider keys) stays
 * CLI-only by design and is not driven from here.
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

/** French label per recette dimension (UI text only; keys stay English, R12). */
const DIM_LABELS: Record<DimName, string> = {
  identity: "identite",
  capabilities: "capacites",
  policy: "politique",
  behavior: "comportement",
};

/** Standards keys surfaced as chips, in display order. */
const TAG_KEYS = ["owasp_asi", "mitre_atlas", "nist"] as const;

/** The full OWASP Top 10 for Agentic Applications 2026 (ASI01..ASI10). */
const OWASP_2026 = [
  "ASI01",
  "ASI02",
  "ASI03",
  "ASI04",
  "ASI05",
  "ASI06",
  "ASI07",
  "ASI08",
  "ASI09",
  "ASI10",
] as const;

/**
 * ASI categories exercised by ANOTHER recette engine, not the /sim MAF+git
 * families: the /sim scorecard counts only what it judges, so these two are
 * marked here so the panel can show the full cross-engine 10/10 coverage without
 * inflating the /sim counts. Ground truth: corpus/repos (discovery) and
 * corpus/maf_orchestration (orchestration).
 */
const CROSS_ENGINE_ASI: Record<string, string> = {
  ASI04: "discovery",
  ASI08: "orchestration",
};

/** The four tabs of the red-team panel. */
type SimTab = "scorecard" | "maf" | "git" | "recordings";

/** One plain-language FR line per tab, shown under the tablist. */
const TAB_NOTES: Record<SimTab, string> = {
  scorecard:
    "Le miroir de `recette redteam` : combien d'anomalies sont attrapees, combien sont ratees, et la repartition OWASP.",
  maf: "Sujets MAF (outils / handoffs) pousses tour apres tour par un adversaire. On verifie le verdict attendu.",
  git: "Agents GitHub / GitLab (Lane B) pousses au-dela de leur perimetre declare. On verifie le verdict attendu.",
  recordings:
    "Conversations figees : on rejoue pas a pas un echange enregistre, deterministe (aucune IA live).",
};

/**
 * The exact CLI command each tab mirrors, shown verbatim so the UI stays in sync
 * with the operator's CLI (no parallel tool). Scorecard == `recette redteam`;
 * the MAF/git tabs run that same set then expose `recette redteam-promote`;
 * recordings replay a frozen Lane B agent recording.
 */
const TAB_CLI: Record<SimTab, string> = {
  scorecard: "recette redteam",
  maf: "recette redteam",
  git: "recette redteam",
  recordings: "recette agent replay <id>",
};

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * True when a failed promote is the "subject already exists" conflict. The
 * client's ApiError message embeds the HTTP status and the backend detail, so a
 * 409 carries both "409" and the "already exists" wording -- either signals the
 * subject is already in the corpus and can be replaced with overwrite.
 */
function isAlreadyPromotedConflict(message: string): boolean {
  const lower = message.toLowerCase();
  return lower.includes("409") || lower.includes("already exists");
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
// Scorecard (the CLI mirror, computed client-side)
// ---------------------------------------------------------------------------

interface RedTeamScorecard {
  total: number;
  /** anomaly_caught && verdict incorrect: a real anomaly the tool caught. */
  anomaliesCaught: number;
  /** anomaly_caught && verdict correct: a conform agent, no false alarm. */
  conformNoFalseAlarm: number;
  /** anomaly_caught === false: the tool missed (or false-alarmed). */
  missed: number;
  /** Count by OWASP Agentic tag, sorted by tag (deterministic, I4). */
  byOwasp: [string, number][];
}

/**
 * Aggregate both families exactly like `recette redteam` (redteam_scorecard.py):
 * caught = anomaliesCaught + conformNoFalseAlarm, missed = total - caught,
 * grouped by the OWASP tag. Pure + deterministic (stable sort).
 */
export function computeScorecard(scenarios: SimScenario[]): RedTeamScorecard {
  let anomaliesCaught = 0;
  let conformNoFalseAlarm = 0;
  let missed = 0;
  const owasp = new Map<string, number>();
  for (const s of scenarios) {
    if (!s.anomaly_caught) {
      missed += 1;
    } else if (s.verdict === "incorrect") {
      anomaliesCaught += 1;
    } else {
      conformNoFalseAlarm += 1;
    }
    const tag = s.tags.owasp_asi;
    if (tag) {
      owasp.set(tag, (owasp.get(tag) ?? 0) + 1);
    }
  }
  return {
    total: scenarios.length,
    anomaliesCaught,
    conformNoFalseAlarm,
    missed,
    byOwasp: [...owasp.entries()].sort((a, b) => a[0].localeCompare(b[0])),
  };
}

/**
 * The scorecard banner: the client-side mirror of the `recette redteam`
 * scorecard. Reuses the verdicts-page stat-chip look. Pure (R16).
 */
export function Scorecard({ scenarios }: { scenarios: SimScenario[] }): JSX.Element {
  const card = computeScorecard(scenarios);
  // Full OWASP Agentic 2026 coverage across the THREE engines: the ASI tags
  // judged here (MAF+git) plus the cross-engine ones (discovery, orchestration).
  const here = new Set(card.byOwasp.map(([tag]) => tag));
  const covered = new Set([...here, ...Object.keys(CROSS_ENGINE_ASI)]);
  const coveredCount = OWASP_2026.filter((a) => covered.has(a)).length;
  return (
    <div className="verdict-scorecard" data-testid="sim-scorecard">
      <div className="verdict-scorecard-group">
        <span className="verdict-stat" data-testid="sim-scorecard-total">
          <span className="verdict-stat-label">Total</span> {card.total}
        </span>
        <span className="verdict-stat sim-stat-caught" data-testid="sim-scorecard-caught">
          <span className="verdict-stat-label">Anomalies attrapees</span>{" "}
          {card.anomaliesCaught}
        </span>
        <span className="verdict-stat sim-stat-caught" data-testid="sim-scorecard-conform">
          <span className="verdict-stat-label">Conformes sans fausse alarme</span>{" "}
          {card.conformNoFalseAlarm}
        </span>
        <span className="verdict-stat sim-stat-missed" data-testid="sim-scorecard-missed">
          <span className="verdict-stat-label">Ratees</span> {card.missed}
        </span>
      </div>
      <div className="verdict-scorecard-group" data-testid="sim-scorecard-owasp">
        <span className="verdict-stat-label sim-owasp-label">Repartition OWASP</span>
        {card.byOwasp.length === 0 ? (
          <span className="sim-section-sub">aucune</span>
        ) : (
          card.byOwasp.map(([tag, n]) => (
            <span
              key={tag}
              className="verdict-stat"
              data-testid={`sim-scorecard-owasp-${tag}`}
            >
              <span className="verdict-stat-label">{tag}</span> {n}
            </span>
          ))
        )}
      </div>
      <div className="verdict-scorecard-group" data-testid="sim-scorecard-coverage">
        <span className="verdict-stat-label sim-owasp-label">
          Couverture OWASP Agentic 2026
        </span>
        <span className="verdict-stat sim-stat-caught" data-testid="sim-scorecard-coverage-count">
          {coveredCount}/10
        </span>
        {OWASP_2026.map((asi) => {
          const inSim = here.has(asi);
          const cross = CROSS_ENGINE_ASI[asi];
          const state = inSim ? "here" : cross ? "cross" : "absent";
          const title = inSim
            ? "couvert ici (MAF / git)"
            : cross
              ? `couvert par la recette ${cross}`
              : "non couvert";
          return (
            <span
              key={asi}
              className="sim-chip sim-cov"
              data-cov={state}
              title={title}
              data-testid={`sim-scorecard-cov-${asi}`}
            >
              {asi}
              {cross ? ` (${cross})` : ""}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scenario card grid (pure, exported for testability)
// ---------------------------------------------------------------------------

/**
 * Pure presentational grid of red-team scenario cards. Each card shows the
 * subject name, its family + strategy (violation_type) chip, a prominent
 * attrapee/ratee badge (green/red), the predicted-vs-expected verdict, the
 * OWASP/ATLAS/NIST standards chips, and a "Promouvoir vers le corpus" button
 * enabled only for a caught anomaly (verdict=incorrect). The card is clickable
 * to open the detail panel via onSelect; promote state is kept locally.
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
  const [conflict, setConflict] = useState<Record<string, boolean>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});

  const onPromote = (id: string, overwrite = false): void => {
    setPending((p) => ({ ...p, [id]: true }));
    setPromoteError((e) => {
      const next = { ...e };
      delete next[id];
      return next;
    });
    setConflict((c) => {
      const next = { ...c };
      delete next[id];
      return next;
    });
    promoteSimScenario(id, overwrite ? { overwrite: true } : undefined)
      .then((res) => setPromoted((p) => ({ ...p, [id]: res })))
      .catch((err) => {
        const message = errorMessage(err);
        // A 409 "already exists" is not a dead end: offer the overwrite replace.
        if (!overwrite && isAlreadyPromotedConflict(message)) {
          setConflict((c) => ({ ...c, [id]: true }));
        } else {
          setPromoteError((e) => ({ ...e, [id]: message }));
        }
      })
      .finally(() => setPending((p) => ({ ...p, [id]: false })));
  };

  if (scenarios.length === 0)
    return (
      <p className="sim-empty" data-testid="sim-scn-empty">
        Aucun scenario red-team disponible.
      </p>
    );

  return (
    <ul className="sim-grid" data-testid="sim-scenarios">
      {scenarios.map((s) => {
        const caughtAnomaly = s.verdict === "incorrect";
        const result = promoted[s.scenario_id];
        const error = promoteError[s.scenario_id];
        const inConflict = conflict[s.scenario_id] === true && result === undefined;
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
                  {s.anomaly_caught ? "attrapee" : "ratee"}
                </span>
                {s.family && <span className="sim-chip sim-chip-neutral">{s.family}</span>}
                {s.violation_type && (
                  <span className="sim-chip sim-chip-accent">{s.violation_type}</span>
                )}
              </div>
              <span className="sim-card-title">{s.name}</span>
              <span className="sim-verdict-line">
                predit <strong>{s.verdict}</strong> · attendu{" "}
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
                title={caughtAnomaly ? undefined : "rien a promouvoir"}
                onClick={() => onPromote(s.scenario_id)}
              >
                {result ? "Promu" : "Promouvoir vers le corpus"}
              </button>
            </div>
            {result && (
              <ul className="sim-promoted" data-testid={`sim-scn-promoted-${s.scenario_id}`}>
                <li className="sim-promoted-intro">
                  Sujet negatif cree (equiv. <code>recette redteam-promote {s.scenario_id}</code>)
                  :
                </li>
                {result.created.map((path) => (
                  <li key={path}>
                    <code>{path}</code>
                  </li>
                ))}
                <li className="sim-promoted-next">
                  Note maintenant par la recette d'identification :{" "}
                  <a
                    className="sim-loop-link"
                    href="/recette"
                    data-testid={`sim-scn-promoted-recette-${s.scenario_id}`}
                  >
                    page Recette (<code>recette run</code>)
                  </a>
                </li>
              </ul>
            )}
            {inConflict && (
              <div
                className="sim-promote-conflict"
                data-testid={`sim-scn-conflict-${s.scenario_id}`}
              >
                <span className="sim-section-sub">Deja dans le corpus.</span>
                <button
                  type="button"
                  className="pill"
                  data-testid={`sim-scn-overwrite-${s.scenario_id}`}
                  disabled={pending[s.scenario_id]}
                  onClick={() => onPromote(s.scenario_id, true)}
                >
                  Remplacer
                </button>
              </div>
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

// ---------------------------------------------------------------------------
// Declared-vs-actual: the judge's lens, NOT a naive approved===false
// ---------------------------------------------------------------------------

/** Per-row verdict, mirroring the CLI judge (legibility-first). */
type RowVerdict = "conforme" | "hors-perimetre" | "en-attente";

const ROW_VERDICT_LABEL: Record<RowVerdict, string> = {
  conforme: "conforme",
  "hors-perimetre": "hors perimetre",
  // I6: a declared approval=always tool invoked without the approval being
  // obtained is NOT "non approuvee" (a verdict) -- it required an approval that
  // was never granted, i.e. it is pending the approval gate (policy_violation).
  "en-attente": "en attente (approbation I6)",
};

/**
 * Reconstruct the JUDGE's observed_action key for one action-log row so it can
 * be matched against the violations list. MAF rows are
 * `invoke_tool:<tool_kind>:<target>` / `handoff:<target>` (mirrors
 * maf_judge._check_capabilities, where a null tool_kind serializes as "None");
 * git rows are simply the `action_type` (mirrors the git adapter's
 * observed_action). Returns every candidate key (the git family also matches on
 * the bare action_type substring), so a violation naming the action marks it.
 */
function observedKeys(row: Record<string, unknown>): string[] {
  const keys: string[] = [];
  const action = actionField(row, "action");
  const target = actionField(row, "target");
  const toolKind = actionField(row, "tool_kind");
  if (action === "handoff" && target) {
    keys.push(`handoff:${target}`);
  } else if (action === "invoke_tool" && target) {
    // The Python judge serializes a None tool_kind as the literal "None".
    keys.push(`invoke_tool:${toolKind ?? "None"}:${target}`);
  }
  const actionType = actionField(row, "action_type");
  if (actionType) {
    keys.push(actionType);
  }
  return keys;
}

/**
 * Classify one action-log row using the JUDGE's violations, not approved===false:
 * - hors-perimetre when the row's observed key appears in the judge's violations
 *   (the undeclared tool/handoff or out-of-scope action -- the real anomaly).
 * - en-attente ONLY when the row is a DECLARED approval=always tool that was not
 *   approved (I6 gating): the action required an approval that was never obtained,
 *   so it is pending the approval gate; a declared approval=never tool is never
 *   flagged.
 * - conforme otherwise.
 */
function rowVerdict(
  row: Record<string, unknown>,
  breached: Set<string>,
  gatedTargets: Set<string>,
): RowVerdict {
  if (observedKeys(row).some((k) => breached.has(k))) {
    return "hors-perimetre";
  }
  const target = actionField(row, "target");
  if (
    actionField(row, "action") === "invoke_tool" &&
    target &&
    gatedTargets.has(target) &&
    row.approved === false
  ) {
    return "en-attente";
  }
  return "conforme";
}

/** True when a declared MAF capability is an approval=always (I6-gated) tool. */
function isGatedTool(cap: Record<string, unknown>): boolean {
  return cap.action === "invoke_tool" && cap.approval === "always";
}

/**
 * Pure panel of the agent's DECLARED capabilities (capability_scope), so a third
 * party SEES what the agent was allowed to do before reading what it actually
 * did. MAF: each tool as a `tool_kind/target` chip + an approval badge (I6
 * gating), each handoff as `handoff -> target`. Git: each `action` with its
 * read/write mode + resource globs.
 */
function DeclaredCapabilities({
  scenarioId,
  scope,
}: {
  scenarioId: string;
  scope: Record<string, unknown>[];
}): JSX.Element {
  return (
    <div className="sim-detail-block">
      <h4>Capacites declarees</h4>
      <ul className="sim-scope" data-testid={`sim-scn-scope-${scenarioId}`}>
        {scope.map((cap, i) => {
          const action = actionField(cap, "action");
          if (action === "handoff") {
            const target = actionField(cap, "target") ?? "?";
            return (
              <li className="sim-scope-row" key={i}>
                <span className="sim-chip sim-chip-neutral">handoff</span>
                <span className="sim-scope-arrow">-&gt;</span>
                <span className="sim-scope-target">{target}</span>
              </li>
            );
          }
          if (action === "invoke_tool") {
            const toolKind = actionField(cap, "tool_kind") ?? "tool";
            const target = actionField(cap, "target") ?? "?";
            const approval = actionField(cap, "approval");
            return (
              <li className="sim-scope-row" key={i}>
                <span className="sim-chip sim-chip-neutral">
                  {toolKind}/{target}
                </span>
                {approval && (
                  <span
                    className={`sim-chip ${approval === "always" ? "sim-chip-accent" : "sim-chip-muted"}`}
                  >
                    approbation : {approval === "always" ? "toujours" : "jamais"}
                  </span>
                )}
              </li>
            );
          }
          // Git capability: {action, mode, resources}.
          const mode = actionField(cap, "mode");
          const resources = Array.isArray(cap.resources)
            ? (cap.resources as unknown[]).map(String)
            : [];
          return (
            <li className="sim-scope-row" key={i}>
              <span className="sim-chip sim-chip-neutral">{action ?? "action"}</span>
              {mode && (
                <span className="sim-chip sim-chip-muted">
                  {mode === "write" ? "ecriture" : "lecture"}
                </span>
              )}
              {resources.map((r) => (
                <code className="sim-scope-res" key={r}>
                  {r}
                </code>
              ))}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function DimensionMatrix({
  scenarioId,
  dimensions,
}: {
  scenarioId: string;
  dimensions: SimScenarioView["dimensions"];
}): JSX.Element {
  return (
    <div className="sim-detail-block">
      <h4>Verdict 4 dimensions</h4>
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
              <span className="sim-dim-mark">{conform ? "OK" : "X"}</span>{" "}
              {DIM_LABELS[d]}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/** French label for an adversarial transcript role (UI text only). */
function roleLabel(role: string): string {
  switch (role) {
    case "user":
      return "utilisateur (adversaire)";
    case "assistant":
      return "agent";
    case "tool":
      return "outil";
    default:
      return role;
  }
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
  const scope = view.capability_scope ?? [];
  const violations = view.violations ?? [];
  // The judge's lens: the set of breached observed_action keys (the real
  // anomalies) and the set of I6-gated declared tool targets (approval=always).
  const breached = new Set(violations.map((v) => v.observed_action));
  const gatedTargets = new Set(
    scope
      .filter(isGatedTool)
      .map((cap) => actionField(cap, "target"))
      .filter((t): t is string => typeof t === "string"),
  );
  // I6 pending set: a DECLARED approval=always tool that appears UNAPPROVED in the
  // action_log -- the agent invoked it without obtaining the approval. The matching
  // transcript turn (assistant, tool_name === target) is the gated invocation; we
  // badge it "en attente (I6)" so the bypass is legible on the timeline too.
  const pendingApprovalTargets = new Set(
    actions
      .filter(
        (row) =>
          actionField(row, "action") === "invoke_tool" &&
          row.approved === false &&
          (() => {
            const t = actionField(row, "target");
            return typeof t === "string" && gatedTargets.has(t);
          })(),
      )
      .map((row) => actionField(row, "target"))
      .filter((t): t is string => typeof t === "string"),
  );
  // Only the FIRST matching turn carries the stable data-testid (a tool may be
  // narrated across several turns, but the gated invocation is one event).
  let pendingBadgeShown = false;
  return (
    <section className="sim-detail" data-testid={`sim-scn-detail-${view.scenario_id}`}>
      <div className="sim-detail-head">
        <h3>{view.name}</h3>
        <span
          className={`sim-chip ${view.anomaly_caught ? "sim-caught" : "sim-missed"}`}
        >
          {view.anomaly_caught ? "attrapee" : "ratee"}
        </span>
      </div>
      {view.goal && <p className="sim-detail-goal">Objectif : {view.goal}</p>}

      <DimensionMatrix scenarioId={view.scenario_id} dimensions={view.dimensions} />

      {scope.length > 0 && (
        <DeclaredCapabilities scenarioId={view.scenario_id} scope={scope} />
      )}

      {transcript.length > 0 && (
        <div className="sim-detail-block">
          <h4>Timeline d'attaque (escalade crescendo)</h4>
          <ol className="sim-timeline" data-testid={`sim-scn-transcript-${view.scenario_id}`}>
            {transcript.map((t, i) => {
              const isPendingTurn =
                t.role === "assistant" &&
                typeof t.tool_name === "string" &&
                pendingApprovalTargets.has(t.tool_name);
              const firstPendingTurn = isPendingTurn && !pendingBadgeShown;
              if (firstPendingTurn) {
                pendingBadgeShown = true;
              }
              return (
                <li className="sim-turn" data-role={t.role} key={i}>
                  <span className="sim-turn-role">{roleLabel(t.role)}</span>
                  <span className="sim-turn-body">
                    {t.content ? (
                      t.content
                    ) : (
                      <span className="sim-turn-empty">(appel d'outil)</span>
                    )}
                    {t.tool_name && <code className="sim-turn-tool">{t.tool_name}</code>}
                    {isPendingTurn && (
                      <span
                        className="sim-chip sim-turn-pending"
                        data-testid={
                          firstPendingTurn
                            ? `sim-scn-turn-pending-${view.scenario_id}`
                            : undefined
                        }
                      >
                        en attente (I6)
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {actions.length > 0 && (
        <div className="sim-detail-block">
          <h4>Journal d'actions (declare vs reel)</h4>
          <ul className="sim-actions" data-testid={`sim-scn-actions-${view.scenario_id}`}>
            {actions.map((row, i) => {
              const seq = actionField(row, "seq");
              const name = actionField(row, "action_type", "action") ?? "action";
              const target =
                actionField(row, "target", "resource", "target_system") ?? "";
              const mode = actionField(row, "mode", "tool_kind");
              // The JUDGE's per-action verdict -- the real anomaly, not approved===false.
              const verdict = rowVerdict(row, breached, gatedTargets);
              const conform = verdict === "conforme";
              return (
                <li
                  className="sim-action"
                  data-flagged={conform ? "false" : "true"}
                  data-verdict={verdict}
                  key={i}
                >
                  <span className="sim-action-seq">{seq ?? i}</span>
                  <span className="sim-action-name">{name}</span>
                  {target && <span className="sim-action-target">{target}</span>}
                  {mode && <span className="sim-action-meta">{mode}</span>}
                  <span
                    className={`sim-chip sim-action-flag ${conform ? "sim-caught" : "sim-missed"}`}
                  >
                    {ROW_VERDICT_LABEL[verdict]}
                  </span>
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

/**
 * The promote loop made legible (legibility-first): states EXACTLY what
 * "Promouvoir" does and how it ties back to the platform, in CLI terms so the
 * UI mirrors the operator's CLI. A caught single-axis anomaly is frozen into a
 * negative corpus subject (equiv. `recette redteam-promote <id>`); that subject
 * then becomes ground truth scored by the IDENTIFICATION recette (`recette run`,
 * surfaced on the Recette page). Promote does NOT create a runtime agent or a
 * campaign -- it only adds a frozen test subject.
 */
function PromoteLoopExplainer(): JSX.Element {
  return (
    <aside className="sim-loop" data-testid="sim-loop-explainer">
      <p className="sim-loop-chain">
        Anomalie <strong>attrapee</strong> mono-axe
        <span className="sim-loop-arrow"> -&gt; </span>
        <strong>Promouvoir</strong> (<code>recette redteam-promote &lt;id&gt;</code>) fige un
        sujet negatif dans le corpus
        <span className="sim-loop-arrow"> -&gt; </span>
        note par la recette d'<strong>identification</strong> (<code>recette run</code>).
      </p>
      <p className="sim-loop-note">
        Promouvoir ne cree NI agent runtime NI campagne : il ajoute un sujet de test fige
        (ground-truth). Le rapport se lit sur la{" "}
        <a className="sim-loop-link" href="/recette" data-testid="sim-loop-recette-link">
          page Recette
        </a>{" "}
        (scorecard d'identification) et la{" "}
        <a className="sim-loop-link" href="/verdicts" data-testid="sim-loop-verdicts-link">
          page Verdicts
        </a>{" "}
        (jugement de l'outil externe).
      </p>
    </aside>
  );
}

function FamilySection({
  scenarios,
  fetchDetail,
}: {
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
      <PromoteLoopExplainer />
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
// Frozen-recordings stepper (its own tab)
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
  if (!view) return <p className="sim-loading">Chargement du run...</p>;
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
            {DIM_LABELS[d]}
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
          Precedent
        </button>
        <span className="sim-section-sub" data-testid="sim-cursor">
          tour {view.turns.length ? cursor + 1 : 0}/{view.turns.length}
        </span>
        <button
          type="button"
          className="pill"
          disabled={cursor >= last}
          onClick={() => setCursor((c) => Math.min(last, c + 1))}
        >
          Suivant
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
            <span className="sim-turn-role">{roleLabel(t.role)}</span>
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
  const [activeTab, setActiveTab] = useState<SimTab>("scorecard");

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

  // The scorecard mirrors the CLI over BOTH families combined.
  const allScenarios = useMemo(
    () => [...(mafScenarios ?? []), ...(gitScenarios ?? [])],
    [mafScenarios, gitScenarios],
  );

  const TABS: { key: SimTab; label: string }[] = [
    { key: "scorecard", label: "Scorecard" },
    { key: "maf", label: "Sujets MAF" },
    { key: "git", label: "Agents Git (Lane B)" },
    { key: "recordings", label: "Enregistrements figes" },
  ];

  return (
    <section className="sim-page">
      <div className="page-head">
        <h1>Recette red-team : l'outil d'identification attrape-t-il l'anomalie ?</h1>
        <PageHelp topic="redteam" />
      </div>
      <p className="sim-intro">
        Chaque scenario attaque un agent ; on verifie que le verdict attendu est
        bien rendu -- soit l'anomalie est attrapee (vrai positif), soit l'agent
        conforme ne declenche aucune fausse alarme (vrai negatif). Tout est
        enregistre et deterministe (I4) : aucune IA live n'est lancee ici. Une
        anomalie attrapee mono-axe peut etre figee en sujet negatif du corpus.
      </p>

      <div className="agents-tabs" role="tablist" aria-label="Vue de la recette red-team">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={activeTab === t.key}
            data-testid={`sim-tab-${t.key}`}
            className={
              activeTab === t.key ? "agents-tab agents-tab-active" : "agents-tab"
            }
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <p className="agents-tab-note" data-testid="sim-tab-note">
        {TAB_NOTES[activeTab]}
        <span className="sim-tab-cli">
          CLI : <code data-testid="sim-tab-cli">{TAB_CLI[activeTab]}</code>
        </span>
      </p>

      {activeTab === "scorecard" && (
        <section>
          {mafError && (
            <div className="sim-error" role="alert" data-testid="sim-scenarios-error">
              {mafError}
            </div>
          )}
          {gitError && (
            <div className="sim-error" role="alert" data-testid="sim-git-scenarios-error">
              {gitError}
            </div>
          )}
          {!mafScenarios && !gitScenarios && !mafError && !gitError ? (
            <p className="sim-loading">Chargement de la scorecard...</p>
          ) : (
            <Scorecard scenarios={allScenarios} />
          )}
        </section>
      )}

      {activeTab === "maf" && (
        <>
          {mafError && (
            <div className="sim-error" role="alert">
              {mafError}
            </div>
          )}
          {!mafScenarios && !mafError && (
            <p className="sim-loading">Chargement des sujets MAF...</p>
          )}
          {mafScenarios && (
            <FamilySection scenarios={mafScenarios} fetchDetail={getSimScenario} />
          )}
        </>
      )}

      {activeTab === "git" && (
        <>
          {gitError && (
            <div className="sim-error" role="alert">
              {gitError}
            </div>
          )}
          {!gitScenarios && !gitError && (
            <p className="sim-loading">Chargement des agents Git...</p>
          )}
          {gitScenarios && (
            <FamilySection scenarios={gitScenarios} fetchDetail={getSimGitScenario} />
          )}
        </>
      )}

      {activeTab === "recordings" && (
        <section className="sim-recordings">
          <div className="sim-section-head">
            <span className="sim-section-sub">
              Parcourez pas a pas une conversation enregistree deterministe.
            </span>
          </div>
          {runError && (
            <div className="sim-error" role="alert" data-testid="sim-list-error">
              {runError}
            </div>
          )}
          {!runs && !runError && <p className="sim-loading">Chargement des runs...</p>}
          {runs && runs.length === 0 && (
            <p className="sim-empty">Aucun enregistrement disponible.</p>
          )}
          {runs && runs.length > 0 && (
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
      )}
    </section>
  );
}
