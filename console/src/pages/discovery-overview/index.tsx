/**
 * Discovery dashboard: the unified operator view over the two discovery surfaces.
 *
 * On load, GET /discovery/overview returns one raw object tying together:
 *  (1) the agent CATALOG (total agents, how many declare tools, tag count) --
 *      with a link to the full /registry page;
 *  (2) the observability REPERAGE tally (tool count + a category distribution
 *      and a capability distribution). The capability view foregrounds the
 *      GOVERNANCE axis (audit + replay): those two capabilities are what make an
 *      agent recettable, so the dashboard marks them distinctly -- with a link
 *      to the full /detect page.
 *
 * The endpoint answers raw (no { success, data } envelope), so the client
 * returns the parsed JSON directly -- nothing is unwrapped here. The page is
 * fail-safe: a fetch error renders inline, and an all-zero overview renders an
 * explicit empty state rather than a crash.
 */

import { useEffect, useState } from "react";
import AssistButton from "../../components/assist/AssistButton";
import { Link } from "react-router-dom";

import { getDiscoveryOverview } from "../../api/client";
import type { DiscoveryOverview } from "../../types/platform";
import DiscoveryStatCard from "./DiscoveryStatCard";
import "./discovery-overview.css";

/** The two capabilities that constitute the governance axis (audit trail +
 *  deterministic replay): the recette emphasises their coverage. */
const GOVERNANCE_CAPABILITIES = new Set(["audit", "replay"]);

/** Turn a distribution map into a stable, sorted (label, count) list so the
 *  rendered order is deterministic regardless of object key order. */
function sortedEntries(map: Record<string, number>): Array<[string, number]> {
  return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
}

export default function DiscoveryPage(): JSX.Element {
  const [overview, setOverview] = useState<DiscoveryOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getDiscoveryOverview()
      .then((o) => {
        if (alive) {
          setOverview(o);
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

  const catalog = overview?.catalog;
  const detect = overview?.detect;
  const surfaces = overview?.surfaces;
  const categories = detect ? sortedEntries(detect.by_category) : [];
  const capabilities = detect ? sortedEntries(detect.by_capability) : [];
  const surfaceDist = surfaces ? sortedEntries(surfaces.detected_per_surface) : [];
  const isEmpty =
    overview !== null &&
    (catalog?.total ?? 0) === 0 &&
    (detect?.tools ?? 0) === 0;

  return (
    <section className="discovery-overview-page">
      <div className="page-head">
        <h1>Discovery</h1>
        <AssistButton topic="dashboard.overview" label="Discovery overview" />
      </div>
      <p className="discovery-overview-note">
        La vue d&apos;ensemble operateur des trois piliers de discovery : le
        catalogue des agents publies (ce qu&apos;ils declarent), le reperage des
        outils d&apos;observabilite (ce qui les trahit dans le code), et les
        surfaces (le tool voit-il l&apos;agent sur le hook et le wire eBPF).
        L&apos;axe de gouvernance -- audit et replay -- est mis en avant : ce sont
        les capacites qui rendent un agent recettable.
      </p>

      {error && (
        <div
          className="discovery-overview-error"
          role="alert"
          data-testid="discovery-overview-error"
        >
          {error}
        </div>
      )}

      {loading && !error && (
        <p
          className="discovery-overview-loading"
          data-testid="discovery-overview-loading"
        >
          Chargement de la vue d&apos;ensemble...
        </p>
      )}

      {overview && (
        <>
          {isEmpty && (
            <div
              className="discovery-overview-empty"
              data-testid="discovery-overview-empty"
            >
              Aucun agent publie ni outil reperable pour l&apos;instant.
            </div>
          )}

          <section
            className="discovery-overview-section"
            data-testid="discovery-overview-catalog"
          >
            <header className="discovery-overview-section-head">
              <h2 className="discovery-overview-section-title">Catalogue</h2>
              <Link
                className="discovery-overview-link"
                to="/registry"
                data-testid="discovery-overview-catalog-link"
              >
                Voir le catalogue complet
              </Link>
            </header>
            <div className="discovery-overview-stats">
              <DiscoveryStatCard
                value={catalog?.total ?? 0}
                label="Agents publies"
                testId="discovery-overview-catalog-total"
              />
              <DiscoveryStatCard
                value={catalog?.with_tools ?? 0}
                label="Avec outils"
                caption="declarent au moins un outil"
                testId="discovery-overview-catalog-with-tools"
              />
              <DiscoveryStatCard
                value={catalog?.tags ?? 0}
                label="Tags"
                caption="union dedupliquee"
                testId="discovery-overview-catalog-tags"
              />
            </div>
          </section>

          <section
            className="discovery-overview-section"
            data-testid="discovery-overview-detect"
          >
            <header className="discovery-overview-section-head">
              <h2 className="discovery-overview-section-title">Reperage</h2>
              <Link
                className="discovery-overview-link"
                to="/detect"
                data-testid="discovery-overview-detect-link"
              >
                Voir le reperage complet
              </Link>
            </header>
            <div className="discovery-overview-stats">
              <DiscoveryStatCard
                value={detect?.tools ?? 0}
                label="Outils reperables"
                testId="discovery-overview-detect-tools"
              />
            </div>

            <div className="discovery-overview-dist-grid">
              <div
                className="discovery-overview-dist"
                data-testid="discovery-overview-by-category"
              >
                <h3 className="discovery-overview-dist-title">Par categorie</h3>
                {categories.length === 0 ? (
                  <p className="discovery-overview-dist-empty">aucune categorie</p>
                ) : (
                  <ul className="discovery-overview-dist-list">
                    {categories.map(([category, count]) => (
                      <li
                        key={category}
                        className="discovery-overview-dist-row"
                        data-testid={`discovery-overview-category-${category}`}
                      >
                        <span className="discovery-overview-dist-label">
                          {category}
                        </span>
                        <span className="discovery-overview-dist-count">
                          {count}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div
                className="discovery-overview-dist"
                data-testid="discovery-overview-by-capability"
              >
                <h3 className="discovery-overview-dist-title">
                  Par capacite
                  <span className="discovery-overview-dist-hint">
                    audit + replay = axe de gouvernance
                  </span>
                </h3>
                {capabilities.length === 0 ? (
                  <p className="discovery-overview-dist-empty">aucune capacite</p>
                ) : (
                  <ul className="discovery-overview-dist-list">
                    {capabilities.map(([capability, count]) => {
                      const governance = GOVERNANCE_CAPABILITIES.has(capability);
                      return (
                        <li
                          key={capability}
                          className={`discovery-overview-dist-row ${governance ? "discovery-overview-dist-row-governance" : ""}`}
                          data-testid={`discovery-overview-capability-${capability}`}
                        >
                          <span className="discovery-overview-dist-label">
                            {capability}
                            {governance && (
                              <span
                                className="discovery-overview-gov-chip"
                                data-testid={`discovery-overview-gov-${capability}`}
                              >
                                gouvernance
                              </span>
                            )}
                          </span>
                          <span className="discovery-overview-dist-count">
                            {count}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          </section>

          <section
            className="discovery-overview-section"
            data-testid="discovery-overview-surfaces"
          >
            <header className="discovery-overview-section-head">
              <h2 className="discovery-overview-section-title">Surfaces</h2>
              <span className="discovery-overview-dist-hint">
                le tool VOIT-il l&apos;agent sur chaque surface (hook + eBPF-wire) ?
              </span>
            </header>
            <div className="discovery-overview-stats">
              <DiscoveryStatCard
                value={surfaces?.total_agents ?? 0}
                label="Agents observes"
                testId="discovery-overview-surfaces-total"
              />
              <DiscoveryStatCard
                value={surfaces?.ghosts ?? 0}
                label="Fantomes"
                caption="vus sur aucune surface"
                testId="discovery-overview-surfaces-ghosts"
              />
            </div>
            <div
              className="discovery-overview-dist"
              data-testid="discovery-overview-by-surface"
            >
              <h3 className="discovery-overview-dist-title">Par surface</h3>
              {surfaceDist.length === 0 ? (
                <p className="discovery-overview-dist-empty">aucune surface</p>
              ) : (
                <ul className="discovery-overview-dist-list">
                  {surfaceDist.map(([surface, count]) => (
                    <li
                      key={surface}
                      className="discovery-overview-dist-row"
                      data-testid={`discovery-overview-surface-${surface}`}
                    >
                      <span className="discovery-overview-dist-label">{surface}</span>
                      <span className="discovery-overview-dist-count">{count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
