/**
 * Recette campaigns page -- read-only catalog of the on-disk governance
 * campaigns (campaigns/**, GET /recette-campaigns). DISTINCT from /campaigns
 * (the CRUD Lane B run-sequences): these are scenarios scored by the gateway
 * harness, listed here with an "Expliquer" eye + modal like agents/subjects, so
 * every backend artifact has a coherent UI. This page never runs or mutates
 * them.
 */
import { useEffect, useState } from "react";

import { listRecetteCampaigns } from "../../api/client";
import type { RecetteCampaignSummary } from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import RecetteCampaignExplainModal from "../../components/RecetteCampaignExplainModal";
import "./recette-campaigns.css";

export default function RecetteCampaignsPage(): JSX.Element {
  const [campaigns, setCampaigns] = useState<RecetteCampaignSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [explainId, setExplainId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listRecetteCampaigns()
      .then((c) => {
        if (alive) setCampaigns(c);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section>
      <div className="page-head">
        <h1>Campagnes recette</h1>
        <PageHelp topic="recette_campaigns" />
      </div>

      <p className="rc-intro">
        Scenarios de gouvernance juges par le harness (action {"->"} verdict attendu).
        Lecture seule -- distinct des campagnes Lane B de la page Campagnes.
      </p>

      {error !== null && (
        <div className="rc-error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="rc-muted">Chargement...</p>
      ) : campaigns.length === 0 ? (
        <p className="rc-muted" data-testid="rc-empty">
          Aucune campagne recette dans campaigns/.
        </p>
      ) : (
        <table className="rc-table" data-testid="rc-table">
          <thead>
            <tr>
              <th>Famille</th>
              <th>Campagne</th>
              <th>Objectif</th>
              <th>Actions</th>
              <th>Agents</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => (
              <tr key={c.id} data-testid={`rc-row-${c.id}`}>
                <td>
                  <span className="rc-family">{c.family}</span>
                </td>
                <td className="rc-name">{c.name || c.id}</td>
                <td className="rc-objective">
                  {c.error !== undefined ? (
                    <span className="rc-invalid" role="alert">
                      invalide: {c.error}
                    </span>
                  ) : (
                    (c.objective ?? "-")
                  )}
                </td>
                <td>{c.action_count}</td>
                <td>{c.agent_count}</td>
                <td>
                  {c.error === undefined && (
                    <button
                      type="button"
                      className="pill"
                      aria-label={`Expliquer ${c.id}`}
                      data-testid={`rc-explain-${c.id}`}
                      onClick={() => setExplainId(c.id)}
                    >
                      Expliquer
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <RecetteCampaignExplainModal
        open={explainId !== null}
        campaignId={explainId}
        onClose={() => setExplainId(null)}
      />
    </section>
  );
}
