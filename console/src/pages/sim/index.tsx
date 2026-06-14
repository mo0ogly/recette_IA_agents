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
import { getSimRuns, getSimView } from "../../api/client";
import type { SimRunSummary, SimView } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import "../discovery/discovery.css";

const DIMS = ["identity", "capabilities", "policy", "behavior"] as const;

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
