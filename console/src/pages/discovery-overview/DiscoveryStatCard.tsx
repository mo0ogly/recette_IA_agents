/**
 * One headline stat in the discovery dashboard, rendered as a card: a big value,
 * a short label and an optional caption. An optional `emphasis` flag marks the
 * governance axis (audit + replay coverage) distinctly -- the recette cares that
 * those two are visible, not hidden. Presentational: the parent supplies values.
 */

export default function DiscoveryStatCard({
  value,
  label,
  caption,
  emphasis = false,
  testId,
}: {
  value: number;
  label: string;
  caption?: string;
  emphasis?: boolean;
  testId?: string;
}): JSX.Element {
  return (
    <article
      className={`discovery-overview-stat ${emphasis ? "discovery-overview-stat-emphasis" : ""}`}
      data-testid={testId}
    >
      <span className="discovery-overview-stat-value" data-testid={testId ? `${testId}-value` : undefined}>
        {value}
      </span>
      <span className="discovery-overview-stat-label">{label}</span>
      {caption && <span className="discovery-overview-stat-caption">{caption}</span>}
    </article>
  );
}
