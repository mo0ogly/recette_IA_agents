/**
 * TabbedModal -- a generic dialog with a tab bar, used by the explain modals to
 * separate different kinds of information (identity, capabilities, scenario,
 * ground-truth). Presentation only: the caller supplies the tabs and content.
 */
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import "./TabbedModal.css";

export interface Tab {
  key: string;
  label: string;
  content: ReactNode;
}

interface Props {
  open: boolean;
  title: string;
  tabs: Tab[];
  onClose: () => void;
}

export default function TabbedModal({ open, title, tabs, onClose }: Props): JSX.Element | null {
  const [active, setActive] = useState(0);

  // Reset to the first tab whenever the modal (re)opens or the tab set changes.
  useEffect(() => {
    if (open) setActive(0);
  }, [open, tabs.length]);

  if (!open || tabs.length === 0) return null;
  const current = tabs[Math.min(active, tabs.length - 1)];

  return (
    <div className="tm-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="tm-modal">
        <div className="tm-head">
          <h2>{title}</h2>
          <button type="button" className="tm-close" onClick={onClose} aria-label="Fermer">
            {"×"}
          </button>
        </div>
        <div className="tm-tabs" role="tablist">
          {tabs.map((t, i) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={i === active}
              className={`tm-tab ${i === active ? "tm-tab-active" : ""}`}
              onClick={() => setActive(i)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="tm-panel" role="tabpanel">
          {current.content}
        </div>
      </div>
    </div>
  );
}
