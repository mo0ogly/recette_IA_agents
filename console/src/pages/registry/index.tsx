/**
 * Registry menu: the agent catalog (discovery catalog, phase C).
 *
 * Lists every agent published to the catalog registry (GET /catalog/summary)
 * with its aggregate counts (total / unique / with tools) and the deduplicated
 * tag union. Each agent is rendered as a card; a tool-less agent is surfaced
 * distinctly rather than hidden. Read-only: the page fetches once and renders.
 * The service unwraps the { success, data } envelope (R16); an empty registry
 * renders an explicit empty state, never a crash.
 */

import { useEffect, useState } from "react";
import { getCatalogSummary } from "../../api/client";
import type { CatalogSummary } from "../../types/platform";
import RegistryAgentCard from "./RegistryAgentCard";
import "./registry.css";

export default function RegistryPage(): JSX.Element {
  const [summary, setSummary] = useState<CatalogSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getCatalogSummary()
      .then((s) => {
        if (alive) {
          setSummary(s);
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

  const counts = summary?.summary;
  const agents = summary?.agents ?? [];

  return (
    <section className="registry-page">
      <h1>Catalogue</h1>
      <p className="registry-note">
        Le registre des agents publies au catalogue : ce que chaque agent declare
        (nom, version, editeur, tags, nombre d&apos;outils). Un agent sans outil
        est un cas limite de discovery -- il est affiche distinctement, jamais
        masque.
      </p>

      {error && (
        <div className="registry-error" role="alert" data-testid="registry-error">
          {error}
        </div>
      )}

      {loading && !error && (
        <p className="registry-loading" data-testid="registry-loading">
          Chargement du catalogue...
        </p>
      )}

      {summary && (
        <>
          {counts && (
            <div className="registry-summary" data-testid="registry-summary">
              <div className="registry-stat">
                <span className="registry-stat-value" data-testid="registry-total">
                  {counts.total}
                </span>
                <span className="registry-stat-label">Agents</span>
              </div>
              <div className="registry-stat">
                <span className="registry-stat-value" data-testid="registry-unique">
                  {counts.unique}
                </span>
                <span className="registry-stat-label">Uniques</span>
              </div>
              <div className="registry-stat">
                <span className="registry-stat-value" data-testid="registry-with-tools">
                  {counts.with_tools}
                </span>
                <span className="registry-stat-label">Avec outils</span>
              </div>
              <div className="registry-stat">
                <span className="registry-stat-value">{counts.tags.length}</span>
                <span className="registry-stat-label">Tags</span>
              </div>
            </div>
          )}

          {counts && counts.tags.length > 0 && (
            <div className="registry-tags" data-testid="registry-tag-union">
              <span className="registry-tags-label">Tags</span>
              {counts.tags.map((tag) => (
                <span key={tag} className="registry-tag">
                  {tag}
                </span>
              ))}
            </div>
          )}

          {agents.length === 0 ? (
            <div className="registry-empty" data-testid="registry-empty">
              Aucun agent publie au catalogue.
            </div>
          ) : (
            <div className="registry-agents" data-testid="registry-agents">
              {agents.map((agent) => (
                <RegistryAgentCard key={agent.name} agent={agent} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
