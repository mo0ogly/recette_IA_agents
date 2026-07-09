/**
 * Step-through viewer for an orchestration run (DevUI-style trace view).
 *
 * Loads GET /subjects/orchestration/{id} and lets the operator step through the
 * routed timeline (handoff hops / turns / tool calls), with the four-dimension
 * verdict and the Mermaid diagram. Read-only; the backend is deterministic (I4).
 * Reuses the existing discovery/pill styles -- no new CSS.
 */

import { useEffect, useState } from "react";
import { getOrchestrationView } from "../../api/client";
import type { RunView } from "../../api/client";

const DIMS = ["identity", "capabilities", "policy", "behavior"] as const;

export default function RunViewer({ agentId }: { agentId: string }): JSX.Element {
  const [view, setView] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    let alive = true;
    setView(null);
    setError(null);
    setCursor(0);
    getOrchestrationView(agentId)
      .then((v) => alive && setView(v))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [agentId]);

  if (error) {
    return (
      <div className="discovery-error" role="alert" data-testid="runview-error">
        {error}
      </div>
    );
  }
  if (!view) return <p className="discovery-loading">Loading run...</p>;

  const last = view.steps.length - 1;

  return (
    <section className="discovery-page" data-testid="runview">
      <h2>
        {view.name} <small>({view.style})</small>
      </h2>

      <div className="discovery-summary">
        <span
          className={`pill ${view.verdict === "correct" ? "pill-ok" : "pill-bad"}`}
          data-testid="runview-verdict"
        >
          {view.verdict}
        </span>
        {DIMS.map((d) => (
          <span
            key={d}
            className={`pill ${view.dimensions[d] ? "pill-ok" : "pill-bad"}`}
            data-testid={`runview-dim-${d}`}
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
        <span className="discovery-stat" data-testid="runview-cursor">
          step {view.steps.length ? cursor + 1 : 0}/{view.steps.length}
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
        {view.steps.map((s) => (
          <li
            key={s.index}
            data-testid={`runview-step-${s.index}`}
            className={s.index === cursor ? "pill-ok" : undefined}
          >
            <code>{s.kind}</code> {s.label}
            {s.kind === "handoff" && s.reason ? (
              <em data-testid={`runview-reason-${s.index}`}> — {s.reason}</em>
            ) : null}
          </li>
        ))}
      </ol>

      {view.violations.length > 0 && (
        <ul data-testid="runview-violations">
          {view.violations.map((v) => (
            <li key={v.observed_action}>
              <code>{v.kind}</code> {v.note}
            </li>
          ))}
        </ul>
      )}

      <pre data-testid="runview-mermaid">{view.mermaid}</pre>
    </section>
  );
}
