/**
 * Contextual AI help button ("bouton IA").
 *
 * Drop-in anywhere in the console: one click sends the topic key (+ id
 * params) to POST /assist/help through the shared AssistProvider; the
 * grounded answer lands in the Copilote IA journal (left dock). The
 * data-assist-topic attribute is the anchor for the Prompts IA page
 * "Localiser dans l'UI" feature.
 */

import { useAssistOptional } from "./AssistProvider";

export default function AssistButton({
  topic,
  label,
  params,
}: {
  topic: string;
  label: string;
  params?: Record<string, string>;
}): JSX.Element | null {
  const assist = useAssistOptional();
  // The button is an enhancement, not a page dependency: outside the provider
  // (standalone page tests) it renders nothing.
  if (assist === null) {
    return null;
  }
  const busy = assist.busyTopics.has(topic);
  return (
    <button
      type="button"
      className="assist-help-btn"
      data-assist-topic={topic}
      data-assist-loc={`assist-${topic.split(".")[0]}`}
      disabled={busy}
      onClick={() => void assist.askHelp(topic, label, params)}
      title={`Demander au Copilote IA: ${label}`}
    >
      {busy ? "IA..." : "IA"}
    </button>
  );
}
