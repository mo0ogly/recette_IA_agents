/**
 * Review step of the agent wizard: previews the composed AgentConfig before
 * create/save, and offers a dry-run -- executing the agent's mock scenario
 * in-memory (no persistence, no real side effect) to show the action log it
 * would produce. Owns only the dry-run result state; the composed config is
 * passed in by the wizard so both share one source of truth.
 */

import { useState } from "react";

import { dryRunAgent } from "../../api/client";
import type { AgentConfig, DryRunResult } from "../../types/platform";
import { errorMessage } from "./agentForm";

export type PreviewResult = { config: AgentConfig } | { error: string };

interface AgentReviewStepProps {
  editingId: string | null;
  preview: PreviewResult;
}

export default function AgentReviewStep({ editingId, preview }: AgentReviewStepProps): JSX.Element {
  const [dryRun, setDryRun] = useState<DryRunResult | null>(null);
  const [dryRunError, setDryRunError] = useState<string | null>(null);
  const [dryRunning, setDryRunning] = useState(false);

  async function handleDryRun(): Promise<void> {
    if ("error" in preview) return;
    setDryRunning(true);
    setDryRunError(null);
    setDryRun(null);
    try {
      setDryRun(await dryRunAgent(preview.config));
    } catch (err) {
      setDryRunError(errorMessage(err));
    } finally {
      setDryRunning(false);
    }
  }

  return (
    <fieldset className="agents-step">
      <legend>Revue -- apercu avant {editingId === null ? "creation" : "sauvegarde"}</legend>
      {"error" in preview ? (
        <p className="agents-error-banner" role="alert">
          Scenario JSON invalide : {preview.error}
        </p>
      ) : (
        <>
          <dl className="agents-preview" data-testid="agents-preview">
            <dt>id</dt>
            <dd>{preview.config.id}</dd>
            <dt>runtime / IA</dt>
            <dd>
              {preview.config.runtime} / {preview.config.ai_mode}
            </dd>
            <dt>target</dt>
            <dd>{preview.config.target_system ?? "(aucun)"}</dd>
            <dt>capability_scope</dt>
            <dd>{(preview.config.capability_scope ?? []).join(", ") || "(aucune)"}</dd>
            <dt>scenario</dt>
            <dd>{(preview.config.scenario ?? []).length} etape(s)</dd>
            <dt>memoire</dt>
            <dd>
              {preview.config.memory ? `fenetre ${preview.config.memory.window}` : "contexte complet"}
            </dd>
            <dt>ground-truth</dt>
            <dd>{preview.config.ground_truth ? "declare" : "(aucun)"}</dd>
          </dl>
          <div className="agents-dryrun">
            <button
              type="button"
              className="agents-btn"
              disabled={dryRunning}
              onClick={() => void handleDryRun()}
            >
              {dryRunning ? "Test en cours..." : "Tester (dry-run, mock, sans sauver)"}
            </button>
            {dryRunError !== null && (
              <p className="agents-error-banner" role="alert">
                Dry-run impossible : {dryRunError}
              </p>
            )}
            {dryRun !== null && (
              <div data-testid="agents-dryrun-result">
                <p className="agents-backends-note">
                  {dryRun.actions.length} action(s) jouee(s) -- rien n'a ete sauve ni execute en
                  reel.
                </p>
                <ol className="agents-dryrun-actions">
                  {dryRun.actions.map((a, i) => (
                    <li key={`${String(a.action_type)}-${i}`}>
                      {String(a.action_type)} @ {String(a.target_system)} / {String(a.resource)}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        </>
      )}
    </fieldset>
  );
}
