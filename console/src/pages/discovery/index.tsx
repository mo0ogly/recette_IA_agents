/**
 * Discovery menu: the unified recette scorecard.
 *
 * Renders GET /subjects/scorecard: identification + MAF + every discovery
 * surface (github, gitlab, temporal, openapi, mcp) in one verdict. Read-only;
 * the backend is deterministic (I4). The mcp surface scans MCP server manifests
 * the same way the github surface scans repos.
 */

import { useEffect, useState } from "react";
import { getRecetteScorecard } from "../../api/client";
import type { RecetteScorecard } from "../../api/client";
import "./discovery.css";

const SURFACE_ORDER = ["github", "gitlab", "temporal", "openapi", "mcp"] as const;

export default function DiscoveryPage(): JSX.Element {
  const [card, setCard] = useState<RecetteScorecard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getRecetteScorecard()
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
    <section className="discovery-page">
      <h1>Discovery recette</h1>
      <p className="discovery-note">
        Unified verdict over the test corpus: identification (the four dimensions),
        the standard-aligned MAF subjects, and every discovery surface. The mcp
        surface scans MCP server manifests just like github scans repositories,
        asserting invariant properties only (detection, count, action coverage,
        relative risk ordering), never opaque scores.
      </p>

      {loading && <p className="discovery-loading">Loading scorecard...</p>}
      {error && (
        <div className="discovery-error" role="alert" data-testid="discovery-error">
          {error}
        </div>
      )}

      {card && (
        <>
          <div className="discovery-summary">
            <span
              className={`discovery-verdict ${card.all_passed ? "ok" : "fail"}`}
              data-testid="discovery-verdict"
            >
              {card.all_passed ? "PASS" : "FAIL"}
            </span>
            <span className="discovery-stat">
              identification {card.identification.passed}/{card.identification.agents}
            </span>
            <span className="discovery-stat">
              maf {card.maf.passed}/{card.maf.agents}
            </span>
            <span className="discovery-stat" data-testid="discovery-orchestration">
              orchestration {card.orchestration.passed}/{card.orchestration.teams}
            </span>
          </div>

          <table className="discovery-table">
            <thead>
              <tr>
                <th>Surface</th>
                <th>Repos</th>
                <th>Passed</th>
                <th>FP</th>
                <th>FN</th>
                <th>Ordering</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {SURFACE_ORDER.filter((s) => card.discovery[s]).map((surface) => {
                const sc = card.discovery[surface];
                return (
                  <tr key={surface} data-testid={`discovery-row-${surface}`}>
                    <td>{surface}</td>
                    <td>{sc.repos}</td>
                    <td>{sc.passed}</td>
                    <td>{sc.false_positives}</td>
                    <td>{sc.false_negatives}</td>
                    <td>{sc.ordering_ok ? "ok" : "BROKEN"}</td>
                    <td className={sc.all_passed ? "ok" : "fail"}>
                      {sc.all_passed ? "PASS" : "FAIL"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
