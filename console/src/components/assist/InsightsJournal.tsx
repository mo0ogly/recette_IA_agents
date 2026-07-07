/**
 * Insights journal of the Copilote IA dock: the consolidated log of every
 * contextual-help answer of the session, newest first. Empty until the
 * operator clicks an AI help button somewhere in the console.
 */

import type { AssistInsight } from "../../types/assist";

export default function InsightsJournal({
  insights,
}: {
  insights: AssistInsight[];
}): JSX.Element {
  if (insights.length === 0) {
    return (
      <div className="assist-empty" data-testid="assist-journal-empty">
        Le journal consolide les reponses des boutons IA de la console. Cliquez un bouton
        &quot;IA&quot; sur une page pour alimenter cette memoire de session.
      </div>
    );
  }

  const newestFirst = [...insights].reverse();
  return (
    <div className="assist-journal" data-testid="assist-journal">
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
