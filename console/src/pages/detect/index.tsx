/**
 * Reperage menu: observability-tool detection.
 *
 * On load, GET /detect/signatures lists every observability tool the scanner can
 * recognise, grouped by category (tracing / gateway / eval / audit / replay), each
 * shown with the literal needles that betray it. Below the catalog, a scan box
 * POSTs free-form text to /detect/scan and renders the returned matches (tool +
 * category badge + the matched needle as evidence); when no tool is detected, an
 * explicit empty state is shown rather than a blank panel.
 *
 * Both endpoints answer raw (no { success, data } envelope), so the client
 * returns the parsed JSON directly -- nothing is unwrapped here. The page is
 * fail-safe: a fetch/scan error renders inline, never a crash.
 */

import { useEffect, useState } from "react";
import { getDetectSignatures, scanForObservability } from "../../api/client";
import type {
  DetectMatch,
  DetectSignature,
  DetectSignatures,
} from "../../types/platform";
import DetectToolCard, { categoryClass } from "./DetectToolCard";
import "./detect.css";

/** Group signatures by category, preserving the catalog's category order. */
function groupByCategory(
  signatures: DetectSignatures,
): Array<{ category: string; tools: DetectSignature[] }> {
  return signatures.categories
    .map((category) => ({
      category,
      tools: signatures.tools.filter((t) => t.category === category),
    }))
    .filter((group) => group.tools.length > 0);
}

export default function DetectPage(): JSX.Element {
  const [signatures, setSignatures] = useState<DetectSignatures | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [text, setText] = useState("");
  const [matches, setMatches] = useState<DetectMatch[] | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    let alive = true;
    getDetectSignatures()
      .then((s) => {
        if (alive) {
          setSignatures(s);
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

  function runScan(): void {
    setScanning(true);
    setScanError(null);
    scanForObservability(text)
      .then((result) => {
        setMatches(result.matches);
        setScanning(false);
      })
      .catch((e) => {
        setScanError(e instanceof Error ? e.message : String(e));
        setScanning(false);
      });
  }

  const groups = signatures ? groupByCategory(signatures) : [];

  return (
    <section className="detect-page">
      <h1>Reperage</h1>
      <p className="detect-note">
        Les outils d&apos;observabilite qu&apos;un scanner peut reperer dans le
        code ou la configuration d&apos;un agent : tracage, passerelle LLM,
        evaluation, audit, replay. Chaque outil est trahi par des indices
        litteraux (nom de package, variable d&apos;environnement). Collez un
        extrait dans la zone de reperage pour voir lesquels y sont detectes.
      </p>

      {error && (
        <div className="detect-error" role="alert" data-testid="detect-error">
          {error}
        </div>
      )}

      {loading && !error && (
        <p className="detect-loading" data-testid="detect-loading">
          Chargement des signatures...
        </p>
      )}

      {signatures && (
        <>
          {signatures.categories.length > 0 && (
            <div className="detect-cats" data-testid="detect-cat-union">
              <span className="detect-cats-label">Categories</span>
              {signatures.categories.map((category) => (
                <span key={category} className={categoryClass(category)}>
                  {category}
                </span>
              ))}
            </div>
          )}

          <div className="detect-catalog" data-testid="detect-catalog">
            {groups.map((group) => (
              <div
                key={group.category}
                className="detect-group"
                data-testid={`detect-group-${group.category}`}
              >
                <h2 className="detect-group-title">
                  <span className={categoryClass(group.category)}>
                    {group.category}
                  </span>
                  <span className="detect-group-count">
                    {group.tools.length}
                  </span>
                </h2>
                <div className="detect-tools">
                  {group.tools.map((tool) => (
                    <DetectToolCard key={tool.tool} signature={tool} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="detect-scan" data-testid="detect-scan">
        <h2 className="detect-scan-title">Reperer dans un extrait</h2>
        <textarea
          className="detect-scan-input"
          data-testid="detect-scan-input"
          aria-label="Texte a reperer"
          placeholder="Collez ici du code ou de la configuration d'agent..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
        />
        <div className="detect-scan-actions">
          <button
            type="button"
            className="detect-scan-button"
            data-testid="detect-scan-button"
            onClick={runScan}
            disabled={scanning}
          >
            {scanning ? "Reperage..." : "Reperer"}
          </button>
        </div>

        {scanError && (
          <div
            className="detect-error"
            role="alert"
            data-testid="detect-scan-error"
          >
            {scanError}
          </div>
        )}

        {matches !== null &&
          (matches.length === 0 ? (
            <div className="detect-empty" data-testid="detect-scan-empty">
              aucun outil detecte
            </div>
          ) : (
            <ul className="detect-matches" data-testid="detect-matches">
              {matches.map((match) => (
                <li
                  key={`${match.tool}:${match.matched}`}
                  className="detect-match"
                  data-testid={`detect-match-${match.tool}`}
                >
                  <span className="detect-match-tool">{match.tool}</span>
                  <span className={categoryClass(match.category)}>
                    {match.category}
                  </span>
                  <code
                    className="detect-match-evidence"
                    data-testid={`detect-match-evidence-${match.tool}`}
                  >
                    {match.matched}
                  </code>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </section>
  );
}
