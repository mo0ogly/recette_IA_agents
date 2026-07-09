/**
 * Discovery menu: the unified recette scorecard.
 *
 * Renders GET /subjects/scorecard: identification + MAF + every discovery
 * surface (github, gitlab, temporal, openapi, mcp) in one verdict. Read-only;
 * the backend is deterministic (I4). The mcp surface scans MCP server manifests
 * the same way the github surface scans repos.
 */

import { useCallback, useEffect, useState } from "react";
import { getDiscoveryCheck, getRecetteScorecard } from "../../api/client";
import type { DiscoveryCheck, RecetteScorecard } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import BenchmarkPanel from "./BenchmarkPanel";
import PrecisionRecallPanel from "./PrecisionRecallPanel";
import "./discovery.css";

const SURFACE_ORDER = ["github", "gitlab", "temporal", "openapi", "mcp"] as const;

export default function DiscoveryPage(): JSX.Element {
  const [card, setCard] = useState<RecetteScorecard | null>(null);
  const [check, setCheck] = useState<DiscoveryCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  /** Replay the recette server-side and refresh the verdict + per-repo detail.
   *  Used on mount and by the Relancer button (the harness is deterministic, I4). */
  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getRecetteScorecard()
      .then((c) => {
        setCard(c);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
    // Per-repo drill-down behind the github surface aggregate; best-effort so a
    // failure never blanks the page.
    getDiscoveryCheck()
      .then((d) => setCheck(d))
      .catch(() => setCheck(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="discovery-page">
      <div className="page-head">
        <h1>Discovery recette</h1>
        <button
          type="button"
          className="discovery-rerun"
          onClick={load}
          disabled={loading}
          data-testid="discovery-rerun"
        >
          {loading ? "Relance..." : "Relancer"}
        </button>
        <PageHelp topic="discovery" />
        <AssistButton topic="agents.list" label="Agents de recette configures" />
      </div>
      <p className="discovery-note">
        Verdict unifie sur le corpus de test : identification (les quatre
        dimensions), les sujets MAF alignes sur le standard, et chaque surface
        discovery. La surface mcp scanne les manifests de serveurs MCP comme
        github scanne les depots, en verifiant uniquement des proprietes
        invariantes (detection, comptage, couverture des actions, ordre de
        risque relatif), jamais des scores opaques.
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

          {check && (
            <section className="discovery-drill" data-testid="discovery-drill">
              <h2 className="discovery-drill-title">
                Detail par repo (github){" "}
                <span className="discovery-drill-rate" data-testid="discovery-drill-rate">
                  detection {Math.round(check.detection_rate * 100)}% -- {check.passed}/
                  {check.total}
                </span>
              </h2>
              <table className="discovery-table">
                <thead>
                  <tr>
                    <th>Repo</th>
                    <th>Detecte</th>
                    <th>Attendu</th>
                    <th>Verdict</th>
                    <th>Raisons</th>
                  </tr>
                </thead>
                <tbody>
                  {check.repos.map((r) => (
                    <tr key={r.repo} data-testid={`discovery-repo-${r.repo}`}>
                      <td>{r.repo}</td>
                      <td>{r.detected ? "oui" : "non"}</td>
                      <td>{r.expected ? "oui" : "non"}</td>
                      <td className={r.passed ? "ok" : "fail"}>
                        {r.passed
                          ? "PASS"
                          : r.false_positive
                            ? "FAUX POSITIF"
                            : r.false_negative
                              ? "FAUX NEGATIF"
                              : "FAIL"}
                      </td>
                      <td className="discovery-repo-detail">
                        {r.detail.length > 0 ? r.detail.join("; ") : "--"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <BenchmarkPanel />
          <PrecisionRecallPanel />
        </>
      )}
    </section>
  );
}
