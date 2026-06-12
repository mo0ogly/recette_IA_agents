/**
 * Per-page help trigger: a small button that opens the detailed help modal
 * for a given topic. Drop one next to each page title.
 */

import { useState } from "react";
import HelpModal from "../HelpModal";
import { HELP_TOPICS } from "./helpTopics";
import type { HelpTopicKey } from "./helpTopics";

export interface PageHelpProps {
  topic: HelpTopicKey;
}

export default function PageHelp(props: PageHelpProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const topic = HELP_TOPICS[props.topic];

  return (
    <>
      <button
        type="button"
        className="help-trigger"
        aria-label={`Ouvrir l'aide : ${topic.title}`}
        onClick={() => setOpen(true)}
      >
        ? Aide
      </button>
      <HelpModal open={open} title={topic.title} onClose={() => setOpen(false)}>
        <p className="help-summary">{topic.summary}</p>
        {topic.body}
      </HelpModal>
    </>
  );
}
