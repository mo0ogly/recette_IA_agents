/**
 * Corpus browser: every test subject across families in one list.
 *
 * Renders GET /subjects -- the unified corpus after the git/MAF fusion:
 * git_agent (github/gitlab action-logs), maf_agent (standard-aligned subjects)
 * and maf_orchestration (multi-agent handoff/sequential/concurrent teams). Each
 * row shows its family, ground-truth category, the broken axis for negatives
 * (violation_type) and the expected verdict. Read-only; the backend is
 * deterministic (I4). Reuses the discovery table styling -- no new CSS.
 */

import { useEffect, useMemo, useState } from "react";
import { listSubjects } from "../../api/client";
import type { CorpusListing, CorpusSubject } from "../../api/client";
import "../discovery/discovery.css";

const ALL = "all";

export default function CorpusPage(): JSX.Element {
  const [listing, setListing] = useState<CorpusListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [family, setFamily] = useState<string>(ALL);

  useEffect(() => {
    let alive = true;
    listSubjects()
      .then((l) => {
        if (alive) {
          setListing(l);
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

  const families = useMemo(
    () => (listing ? Object.keys(listing.families).sort() : []),
    [listing],
  );

  const rows = useMemo<CorpusSubject[]>(() => {
    if (!listing) return [];
    return family === ALL
      ? listing.subjects
      : listing.subjects.filter((s) => s.family === family);
  }, [listing, family]);

  return (
    <section className="discovery-page">
      <h1>Corpus</h1>
      <p className="discovery-note">
        Every test subject across families: git agents, standard-aligned MAF
        subjects, and multi-agent orchestration teams (handoff, sequential,
        concurrent). Negatives carry the single broken axis (violation_type).
      </p>

      {loading && <p className="discovery-loading">Loading corpus...</p>}
      {error && (
        <div className="discovery-error" role="alert" data-testid="corpus-error">
          {error}
        </div>
      )}

      {listing && (
        <>
          <div className="discovery-summary">
            <span className="discovery-stat" data-testid="corpus-count">
              {listing.count} subjects
            </span>
            {families.map((f) => (
              <button
                key={f}
                type="button"
                className={`pill ${family === f ? "pill-ok" : ""}`}
                data-testid={`corpus-filter-${f}`}
                onClick={() => setFamily(family === f ? ALL : f)}
              >
                {f} {listing.families[f]}
              </button>
            ))}
          </div>

          <table className="discovery-table">
            <thead>
              <tr>
                <th>Subject</th>
                <th>Family</th>
                <th>Category</th>
                <th>Broken axis</th>
                <th>Expected</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={`${s.family}-${s.agent_id}`} data-testid={`corpus-row-${s.agent_id}`}>
                  <td>{s.agent_id}</td>
                  <td>{s.family}</td>
                  <td>{s.category ?? "-"}</td>
                  <td>{s.violation_type ?? "-"}</td>
                  <td className={s.expected_verdict === "correct" ? "ok" : "fail"}>
                    {s.expected_verdict ?? "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
