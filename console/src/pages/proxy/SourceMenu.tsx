/**
 * SourceMenu -- the source switcher of the Proxy console.
 *
 * Renders the source registry (`SOURCE_DESCRIPTORS`) as an accessible segmented
 * menu: one button per view, each carrying its label, a one-line hint, and a
 * live badge fed by the mounted panel's reported status (trace/flow/bypass
 * count, or "off" when the backend feature is disabled). Presentational only --
 * it owns no polling and no source state; the orchestrator passes the active id,
 * the selection callback, and the per-source status map.
 *
 * A11y: a `role="group"` of `aria-pressed` toggle buttons (not a tablist) so the
 * buttons stay queryable by accessible name and need no roving-tabindex
 * keyboard contract the views do not implement.
 */

import type { SourceDescriptor, SourceId, SourceStatus } from "./proxyMenu";
import { badgeLabel, badgeOutcome } from "./proxyMenu";

interface SourceMenuProps {
  sources: readonly SourceDescriptor[];
  active: SourceId;
  onSelect: (id: SourceId) => void;
  statusById: Partial<Record<SourceId, SourceStatus>>;
}

export default function SourceMenu({
  sources,
  active,
  onSelect,
  statusById,
}: SourceMenuProps): JSX.Element {
  return (
    <div className="proxy-source-menu" role="group" aria-label="source">
      {sources.map((s) => {
        const status = statusById[s.id];
        const outcome = badgeOutcome(status);
        const label = badgeLabel(status);
        return (
          <button
            key={s.id}
            type="button"
            className="proxy-source-item"
            data-active={s.id === active}
            aria-pressed={s.id === active}
            onClick={() => onSelect(s.id)}
          >
            <span className="proxy-source-head">
              <span className="proxy-source-label">{s.label}</span>
              {label !== "" && (
                <span
                  className="proxy-badge proxy-source-badge"
                  data-outcome={outcome}
                  aria-hidden="true"
                >
                  {label}
                </span>
              )}
            </span>
            <span className="proxy-source-hint">{s.hint}</span>
          </button>
        );
      })}
    </div>
  );
}
