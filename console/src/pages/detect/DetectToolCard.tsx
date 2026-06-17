/**
 * One detectable observability tool, rendered as a card: name + category badge
 * and the literal needles that betray it (the evidence a scanner looks for).
 * Presentational: the parent supplies the signature.
 */

import type { DetectSignature } from "../../types/platform";

/** Map a category to a stable CSS modifier so each category gets a distinct badge. */
export function categoryClass(category: string): string {
  return `detect-cat detect-cat-${category}`;
}

export default function DetectToolCard({
  signature,
}: {
  signature: DetectSignature;
}): JSX.Element {
  return (
    <article
      className="detect-tool"
      data-testid={`detect-tool-${signature.tool}`}
    >
      <header className="detect-tool-head">
        <span className="detect-tool-name">{signature.tool}</span>
        <span
          className={categoryClass(signature.category)}
          data-testid={`detect-tool-cat-${signature.tool}`}
        >
          {signature.category}
        </span>
      </header>
      <div className="detect-tool-needles">
        {signature.needles.map((needle) => (
          <span key={needle} className="detect-needle">
            {needle}
          </span>
        ))}
      </div>
    </article>
  );
}
