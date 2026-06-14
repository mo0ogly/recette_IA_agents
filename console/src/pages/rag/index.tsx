/**
 * RAG menu: the retrieval-quality recette scorecard.
 *
 * Renders GET /rag/scorecard: per-query precision / recall / ordering against
 * invariant ground truth (which docs are relevant, which ranks first), never
 * the opaque internal scores. Read-only; the backend is deterministic (I4).
 */

import { useEffect, useState } from "react";
import { getRagScorecard } from "../../api/client";
import type { RagScorecard } from "../../types/platform";
import KnowledgeBaseManager from "./KnowledgeBaseManager";
import "./rag.css";

export default function RagPage(): JSX.Element {
  const [card, setCard] = useState<RagScorecard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getRagScorecard()
      .then((c) => {
        if (alive) {
          setCard(c);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
    <section className="rag-page">
      <h1>RAG retrieval recette</h1>
      <p className="rag-note">
        Deterministic retrieval quality vs invariant ground truth: which docs are
        relevant for a query and which one should rank first, never the opaque
        internal scores. A tool with different scoring still passes if it surfaces
        the right docs in a sane order.
      </p>

      {loading && <p className="rag-loading">Loading scorecard...</p>}
      {error && (
        <div className="rag-error" role="alert" data-testid="rag-error">
          {error}
        </div>
      )}

      {card && (
        <>
          <div className="rag-summary">
            <span
              className={`rag-verdict ${card.all_passed ? "ok" : "fail"}`}
              data-testid="rag-verdict"
            >
              {card.all_passed ? "PASS" : "FAIL"}
            </span>
            <span className="rag-stat">
              {card.passed}/{card.total} queries
            </span>
            <span className="rag-stat">mean precision {card.mean_precision.toFixed(2)}</span>
            <span className="rag-stat">mean recall {card.mean_recall.toFixed(2)}</span>
          </div>

          {card.results.length === 0 ? (
            <p className="rag-empty">No queries in the ground-truth set.</p>
          ) : (
            <table className="rag-table">
              <thead>
                <tr>
                  <th>Query</th>
                  <th>Retrieved</th>
                  <th>Prec.</th>
                  <th>Recall</th>
                  <th>Top</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {card.results.map((r) => (
                  <tr key={r.query} data-testid="rag-row">
                    <td>{r.query}</td>
                    <td className="rag-ids">{r.retrieved.join(", ")}</td>
                    <td>{r.precision.toFixed(2)}</td>
                    <td>{r.recall.toFixed(2)}</td>
                    <td>{r.top_ok ? "ok" : "miss"}</td>
                    <td>
                      <span className={`rag-pill ${r.passed ? "ok" : "fail"}`}>
                        {r.passed ? "PASS" : "FAIL"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
    <KnowledgeBaseManager />
    </>
  );
}
