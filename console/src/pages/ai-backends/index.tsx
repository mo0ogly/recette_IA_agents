/**
 * AI backends page -- the multi-provider IA interface, promoted from a panel
 * buried in the Agents page to its own nav tab.
 *
 * Lists / creates / deletes / tests the AI backends agents bind to. The
 * provider dropdown is served from GET /config/ai-providers (the catalog
 * derived from recette/llm.py's factory), so a provider added server-side
 * surfaces here with no frontend change. Provider keys are write-only (R8): the
 * console sends a key but never reads one back, it only renders the
 * key_configured status. The heavy lifting lives in the reused
 * AiBackendsPanel; this page only owns the data load + error surface.
 */

import { useCallback, useEffect, useState } from "react";

import { listAiBackends } from "../../api/client";
import type { AiBackend } from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import AiBackendsPanel from "../agents/AiBackendsPanel";
import "../agents/agents.css";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export default function AiBackendsPage(): JSX.Element {
  const [backends, setBackends] = useState<AiBackend[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setBackends(await listAiBackends());
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div>
      <div className="page-head">
        <h1>IA (backends)</h1>
        <PageHelp topic="ai_backends" />
        <AssistButton topic="ai_backends.list" label="Backends IA configures" />
      </div>

      {error !== null && (
        <div className="agents-error-banner" role="alert">
          {error}
        </div>
      )}

      <AiBackendsPanel backends={backends} onChanged={refresh} onError={setError} />
    </div>
  );
}
