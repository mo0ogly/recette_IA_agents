/**
 * Prompts IA page: the operator-editable prompt catalog of the Copilote IA.
 *
 * Lists every catalog entry grouped by the console view it applies to
 * (localisation.view), with a "modifie" badge on overridden prompts, an edit
 * modal (Monaco), a reset-to-default action, and "Localiser dans l'UI" which
 * navigates to the view with ?assist-locate=<loc> (the matching AI trigger
 * flashes there).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listAssistPrompts, resetAssistPrompt } from "../../api/assistClient";
import PageHelp from "../../components/help/PageHelp";
import type { AssistPromptEntry } from "../../types/assist";

import PromptEditModal from "./PromptEditModal";
import "./iaPrompts.css";

function valuePreview(entry: AssistPromptEntry): string {
  const text =
    entry.kind === "text" ? String(entry.value ?? "") : JSON.stringify(entry.value ?? {});
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
}

export default function IaPromptsPage(): JSX.Element {
  const navigate = useNavigate();
  const [prompts, setPrompts] = useState<AssistPromptEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AssistPromptEntry | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    listAssistPrompts()
      .then((response) => {
        setPrompts(response.prompts);
        setError(null);
      })
      .catch((exc) => setError(exc instanceof Error ? exc.message : String(exc)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const groups = useMemo(() => {
    const byView = new Map<string, AssistPromptEntry[]>();
    for (const entry of prompts) {
      const view = entry.localisation.view;
      const bucket = byView.get(view);
      if (bucket === undefined) {
        byView.set(view, [entry]);
      } else {
        bucket.push(entry);
      }
    }
    return [...byView.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [prompts]);

  async function reset(entry: AssistPromptEntry): Promise<void> {
    try {
      await resetAssistPrompt(entry.id);
      load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  function locate(entry: AssistPromptEntry): void {
    navigate(
      `${entry.localisation.view}?assist-locate=${encodeURIComponent(entry.localisation.loc)}`,
    );
  }

  return (
    <div>
      <div className="page-head">
        <h1>Prompts IA</h1>
        <PageHelp topic="ia_prompts" />
      </div>
      <p className="iaprompts-intro">
        Les prompts du Copilote IA (chat du dock et boutons d&apos;aide contextuelle). Les
        valeurs par defaut vivent dans le code; seules vos personnalisations sont
        persistees, appliquees au prochain appel sans redemarrage.
      </p>
      {error !== null ? (
        <div className="assist-error" role="alert">
          {error}
        </div>
      ) : null}
      {loading ? <div className="assist-empty">Chargement du catalogue...</div> : null}
      {groups.map(([view, entries]) => (
        <section key={view} className="panel iaprompts-group">
          <h2>
            Vue <span className="mono">{view}</span>
          </h2>
          <table data-testid={`iaprompts-group-${view.replace(/\//g, "")}`}>
            <thead>
              <tr>
                <th>Prompt</th>
                <th>Type</th>
                <th>Declencheur</th>
                <th>Valeur</th>
                <th>Etat</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td>
                    <div className="iaprompts-label">{entry.label}</div>
                    <div className="mono iaprompts-id">{entry.id}</div>
                  </td>
                  <td>
                    <span className="mono">{entry.kind}</span>
                  </td>
                  <td>{entry.localisation.trigger}</td>
                  <td className="iaprompts-preview">{valuePreview(entry)}</td>
                  <td>
                    {entry.overridden ? (
                      <span className="badge-amber iaprompts-badge">modifie</span>
                    ) : (
                      <span className="badge-gray iaprompts-badge">defaut</span>
                    )}
                  </td>
                  <td className="iaprompts-actions">
                    <button type="button" onClick={() => setEditing(entry)}>
                      Modifier
                    </button>
                    <button
                      type="button"
                      onClick={() => void reset(entry)}
                      disabled={!entry.overridden}
                    >
                      Reinitialiser
                    </button>
                    <button type="button" onClick={() => locate(entry)}>
                      Localiser dans l&apos;UI
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
      {editing !== null ? (
        <PromptEditModal
          entry={editing}
          onSaved={() => {
            setEditing(null);
            load();
          }}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  );
}
