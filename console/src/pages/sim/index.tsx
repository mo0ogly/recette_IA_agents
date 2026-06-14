/**
 * Red-team / simulation runs viewer.
 *
 * Lists GET /sim/runs (frozen, deterministic conversations) and steps through a
 * selected run: the transcript turns, the per-turn checks, the action log and the
 * four-dimension verdict. The runs are RECORDED -- the console never triggers a
 * live LLM. Read-only; the backend is deterministic (I4). Reuses the discovery
 * styling -- no new CSS.
 */

import { useEffect, useMemo, useState } from "react";
import {
  getSimRuns,
  getSimScenarios,
  getSimView,
  promoteSimScenario,
} from "../../api/client";
import type {
  SimPromoteResult,
  SimRunSummary,
  SimScenario,
  SimView,
} from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import "../discovery/discovery.css";

const DIMS = ["identity", "capabilities", "policy", "behavior"] as const;

/**
 * Pure presentational list of red-team scenarios. For each scenario it surfaces,
 * legibility-first, whether the recette caught the anomaly (a pill-ok "caught" /
 * pill-bad "missed" badge keyed off anomaly_caught), the predicted-vs-expected
 * verdict, and the OWASP ASI tag when the scenario carries one. A CAUGHT anomaly
 * (verdict=incorrect) carries a "Promote to corpus" action that freezes it into a
 * negative corpus subject (POST /sim/scenarios/{id}/promote) and surfaces the
 * created paths; a true negative (verdict=correct) shows the action disabled --
 * nothing to promote. Promote state is kept locally per scenario id (R16).
 */
export function ScenarioList({ scenarios }: { scenarios: SimScenario[] }): JSX.Element {
  const [promoted, setPromoted] = useState<Record<string, SimPromoteResult>>({});
  const [promoteError, setPromoteError] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});

  if (scenarios.length === 0)
    return (
      <p className="discovery-note" data-testid="sim-scn-empty">
        No red-team scenarios.
      </p>
    );

  const onPromote = (id: string): void => {
    setPending((p) => ({ ...p, [id]: true }));
    setPromoteError((e) => {
      const next = { ...e };
      delete next[id];
      return next;
    });
    promoteSimScenario(id)
      .then((res) => setPromoted((p) => ({ ...p, [id]: res })))
      .catch((err) =>
        setPromoteError((e) => ({
          ...e,
          [id]: err instanceof Error ? err.message : String(err),
        })),
      )
      .finally(() => setPending((p) => ({ ...p, [id]: false })));
  };

  return (
    <ul className="discovery-summary" data-testid="sim-scenarios">
      {scenarios.map((s) => {
        const caughtAnomaly = s.verdict === "incorrect";
        const result = promoted[s.scenario_id];
        const error = promoteError[s.scenario_id];
        return (
          <li key={s.scenario_id} data-testid={`sim-scn-${s.scenario_id}`}>
            <span
              className={`pill ${s.anomaly_caught ? "pill-ok" : "pill-bad"}`}
              data-testid={`sim-scn-caught-${s.scenario_id}`}
            >
              {s.anomaly_caught ? "caught" : "missed"}
            </span>{" "}
            <strong>{s.name}</strong>{" "}
            <span className="discovery-stat">
              {s.verdict} (expected {s.expected_verdict})
            </span>
            {s.tags.owasp_asi && (
              <span className="pill" data-testid={`sim-scn-owasp-${s.scenario_id}`}>
                {s.tags.owasp_asi}
              </span>
            )}{" "}
            {caughtAnomaly ? (
              <button
                type="button"
                className="pill"
                data-testid={`sim-scn-promote-${s.scenario_id}`}
                disabled={pending[s.scenario_id] || result !== undefined}
                onClick={() => onPromote(s.scenario_id)}
              >
                Promote to corpus
              </button>
            ) : (
              <button
                type="button"
                className="pill"
                data-testid={`sim-scn-promote-${s.scenario_id}`}
                disabled
                title="nothing to promote"
              >
                Promote to corpus
              </button>
            )}
            {result && (
              <ul
                className="discovery-summary"
                data-testid={`sim-scn-promoted-${s.scenario_id}`}
              >
                {result.created.map((path) => (
                  <li key={path}>
                    <code>{path}</code>
                  </li>
                ))}
              </ul>
            )}
            {error && (
              <span
                className="discovery-error"
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
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [agentId]);

  if (error)
    return (
      <div className="discovery-error" role="alert" data-testid="sim-error">
        {error}
      </div>
    );
  if (!view) return <p className="discovery-loading">Loading run...</p>;
  const last = view.turns.length - 1;

  return (
    <section data-testid="sim-view">
      <h2>{view.name}</h2>
      <div className="discovery-summary">
        <span
          className={`pill ${view.verdict === "correct" ? "pill-ok" : "pill-bad"}`}
          data-testid="sim-verdict"
        >
          {view.verdict}
        </span>
        <span className="discovery-stat" data-testid="sim-stopped">
          {view.stopped_reason}
        </span>
        {DIMS.map((d) => (
          <span
            key={d}
            className={`pill ${view.dimensions[d] ? "pill-ok" : "pill-bad"}`}
            data-testid={`sim-dim-${d}`}
          >
            {d}
          </span>
        ))}
      </div>

      <div className="discovery-summary">
        <button
          type="button"
          className="pill"
          disabled={cursor <= 0}
          onClick={() => setCursor((c) => Math.max(0, c - 1))}
        >
          Prev
        </button>
        <span className="discovery-stat" data-testid="sim-cursor">
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

      <ol>
        {view.turns.map((t) => (
          <li
            key={t.index}
            data-testid={`sim-turn-${t.index}`}
            className={t.index === cursor ? "pill-ok" : undefined}
          >
            <code>{t.role}</code> {t.content}
          </li>
        ))}
      </ol>

      {view.checks.length > 0 && (
        <ul data-testid="sim-checks">
          {view.checks.map((c, i) => (
            <li key={i} className={c.passed ? "ok" : "fail"}>
              {c.passed ? "PASS" : "FAIL"} {c.reason}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function SimPage(): JSX.Element {
  const [runs, setRuns] = useState<SimRunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<SimScenario[] | null>(null);
  const [scenariosError, setScenariosError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getSimRuns()
      .then((r) => {
        if (alive) {
          setRuns(r.runs);
          setOpen(r.runs[0]?.agent_id ?? null);
        }
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    getSimScenarios()
      .then((r) => alive && setScenarios(r.scenarios))
      .catch((e) => alive && setScenariosError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const body = useMemo(() => open && <Viewer agentId={open} />, [open]);

  return (
    <section className="discovery-page">
      <div className="page-head">
        <h1>Red-team &amp; simulation</h1>
        <PageHelp topic="corpus" />
      </div>
      <p className="discovery-note">
        Frozen, deterministic conversations: a subject driven through adversarial
        turns, with per-turn checks and the four-dimension verdict. Recorded runs --
        no live LLM is triggered here.
      </p>

      {error && (
        <div className="discovery-error" role="alert" data-testid="sim-list-error">
          {error}
        </div>
      )}
      {!runs && !error && <p className="discovery-loading">Loading runs...</p>}

      <h2>Red-team scenarios</h2>
      <p className="discovery-note">
        Each scenario carries an expected verdict; the badge shows whether the
        recette caught the anomaly, alongside its OWASP ASI tag.
      </p>
      {scenariosError && (
        <div className="discovery-error" role="alert" data-testid="sim-scenarios-error">
          {scenariosError}
        </div>
      )}
      {!scenarios && !scenariosError && (
        <p className="discovery-loading">Loading scenarios...</p>
      )}
      {scenarios && <ScenarioList scenarios={scenarios} />}

      {runs && (
        <div className="discovery-summary">
          {runs.map((r) => (
            <button
              key={r.agent_id}
              type="button"
              className={`pill ${open === r.agent_id ? "pill-ok" : ""}`}
              data-testid={`sim-run-${r.agent_id}`}
              onClick={() => setOpen(r.agent_id)}
            >
              {r.name} · {r.verdict}
            </button>
          ))}
        </div>
      )}

      {body}
    </section>
  );
}
