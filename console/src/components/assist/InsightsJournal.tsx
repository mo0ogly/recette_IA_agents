/**
 * Insights journal of the Copilote IA dock: the consolidated log of every
 * contextual-help answer of the session, newest first. Empty until the
 * operator clicks an AI help button somewhere in the console.
 */

import { useMemo, useState } from "react";

import type { AssistInsight } from "../../types/assist";

export default function InsightsJournal({
  insights,
}: {
  insights: AssistInsight[];
}): JSX.Element {
  const [filter, setFilter] = useState("");

  const newestFirst = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const ordered = [...insights].reverse();
    if (needle.length === 0) {
      return ordered;
    }
    return ordered.filter(
      (i) =>
        i.label.toLowerCase().includes(needle) ||
        i.topic.toLowerCase().includes(needle) ||
        i.answer.toLowerCase().includes(needle),
    );
  }, [insights, filter]);

  if (insights.length === 0) {
    return (
      <div className="assist-empty" data-testid="assist-journal-empty">
        Le journal consolide les reponses des boutons IA de la console. Cliquez un bouton
        &quot;IA&quot; sur une page pour alimenter cette memoire de session.
      </div>
    );
  }

  return (
    <div className="assist-journal" data-testid="assist-journal">
      <input
        type="search"
        className="assist-journal-filter"
        placeholder="Filtrer le journal..."
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        aria-label="Filtrer le journal"
      />
      {newestFirst.length === 0 ? (
        <div className="assist-empty" data-testid="assist-journal-nomatch">
          Aucune entree ne correspond a &quot;{filter}&quot;.
        </div>
      ) : null}
      {newestFirst.map((insight) => (
        <article key={insight.id} className="assist-insight">
          <header className="assist-insight-head">
            <span className="assist-insight-label">{insight.label}</span>
            <span className="assist-insight-topic mono">{insight.topic}</span>
          </header>
          <p className="assist-insight-body">{insight.answer}</p>
        </article>
      ))}
    </div>
  );
}
