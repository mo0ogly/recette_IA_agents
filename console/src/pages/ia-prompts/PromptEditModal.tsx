/**
 * Edit modal of the Prompts IA page: Monaco (lazy) over one catalog entry.
 * text prompts edit as plain text; json prompts are parsed on save (invalid
 * JSON never reaches the API). Saving calls PUT /assist/prompts/{id}; the
 * parent refreshes the catalog from the response.
 */

import { Suspense, lazy, useState } from "react";

import { setAssistPrompt } from "../../api/assistClient";
import type { AssistPromptEntry } from "../../types/assist";

const MonacoPromptEditor = lazy(() => import("./MonacoPromptEditor"));

function entryText(entry: AssistPromptEntry): string {
  if (entry.kind === "text") {
    return String(entry.value ?? "");
  }
  return JSON.stringify(entry.value, null, 2);
}

export default function PromptEditModal({
  entry,
  onSaved,
  onClose,
}: {
  entry: AssistPromptEntry;
  onSaved: (updated: AssistPromptEntry) => void;
  onClose: () => void;
}): JSX.Element {
  const [draft, setDraft] = useState<string>(() => entryText(entry));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(): Promise<void> {
    let value: unknown = draft;
    if (entry.kind === "json") {
      try {
        value = JSON.parse(draft);
      } catch {
        setError("JSON invalide: corrigez la syntaxe avant d'enregistrer.");
        return;
      }
    } else if (draft.trim().length === 0) {
      setError("Le prompt ne peut pas etre vide.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await setAssistPrompt(entry.id, value);
      onSaved(updated);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-dialog iaprompts-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Modifier ${entry.label}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="iaprompts-modal-head">
          <div>
            <h2>{entry.label}</h2>
            <p className="iaprompts-modal-desc">{entry.description}</p>
          </div>
          <span className="mono iaprompts-modal-id">{entry.id}</span>
        </header>
        <Suspense fallback={<div className="assist-empty">Chargement de l&apos;editeur...</div>}>
          <MonacoPromptEditor
            value={draft}
            language={entry.kind === "json" ? "json" : "plaintext"}
            onChange={setDraft}
          />
        </Suspense>
        {error !== null ? (
          <div className="assist-error" role="alert">
            {error}
          </div>
        ) : null}
        <footer className="iaprompts-modal-actions">
          <button type="button" onClick={onClose} disabled={saving}>
            Annuler
          </button>
          <button
            type="button"
            className="iaprompts-save-btn"
            onClick={() => void save()}
            disabled={saving}
          >
            {saving ? "Enregistrement..." : "Enregistrer"}
          </button>
        </footer>
      </div>
    </div>
  );
}
