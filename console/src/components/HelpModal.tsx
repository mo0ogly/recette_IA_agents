/**
 * Reusable modal dialog used by the per-page help system.
 *
 * Rendered as an overlay above the page. It is accessible (role="dialog",
 * aria-modal, labelled by its title), closes on Escape and on backdrop click,
 * and traps the initial focus on the close button. It renders nothing when
 * `open` is false, so callers can mount it unconditionally.
 */

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

export interface HelpModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export default function HelpModal(props: HelpModalProps): JSX.Element | null {
  const { open, title, onClose, children } = props;
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    closeRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const titleId = "help-modal-title";

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
      data-testid="help-modal-backdrop"
    >
      <div
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button
            ref={closeRef}
            type="button"
            className="modal-close"
            aria-label="Fermer l'aide"
            onClick={onClose}
          >
            X
          </button>
        </header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
