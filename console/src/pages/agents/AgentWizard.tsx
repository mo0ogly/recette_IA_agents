/**
 * Agent creation/edit wizard: the agent form presented as a guided stepper
 * (Identite -> Cible -> IA -> Tools -> Memoire -> Ground-truth -> Revue) with
 * a pre-create preview of the composed AgentConfig. All state is owned by the
 * orchestrator; this component renders steps and delegates via callbacks.
 *
 * The wizard is purely a navigation shell over the same fields: editing an
 * existing agent jumps straight to the full form (all steps reachable), and
 * the final Revue step shows exactly what will be created/saved so a third
 * party can read the agent's declared behaviour before it runs (legibility).
 */

import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import type { CorpusSubject } from "../../api/client";
import type { AgentAction, AgentConfig, AiBackend } from "../../types/platform";
import type { AgentFormValues } from "./agentForm";
import { errorMessage, toAgentConfig } from "./agentForm";
import AgentGroundTruthStep from "./AgentGroundTruthStep";

interface AgentWizardProps {
  editingId: string | null;
  form: AgentFormValues;
  setField: <K extends keyof AgentFormValues>(key: K, value: AgentFormValues[K]) => void;
  toggleAction: (action: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  catalogSystems: string[];
  scopedActions: AgentAction[];
  backends: AiBackend[];
  subjects: CorpusSubject[];
}

const STEPS = ["Identite", "Cible", "IA", "Tools", "Memoire", "Ground-truth", "Revue"] as const;

/** Compose the would-be AgentConfig for the preview, or an error string when
 *  the advanced scenario JSON does not parse. Pure, no side effect. */
function previewConfig(
  form: AgentFormValues,
  id: string,
): { config: AgentConfig } | { error: string } {
  try {
    return { config: toAgentConfig(form, id || "(id)") };
  } catch (err) {
    return { error: errorMessage(err) };
  }
}

export default function AgentWizard({
  editingId,
  form,
  setField,
  toggleAction,
  onSubmit,
  onCancel,
  catalogSystems,
  scopedActions,
  backends,
  subjects,
}: AgentWizardProps): JSX.Element {
  const [step, setStep] = useState(0);
  const isLast = step === STEPS.length - 1;
  const previewId = editingId ?? form.id.trim();
  const preview = useMemo(() => previewConfig(form, previewId), [form, previewId]);

  return (
    <form className="agents-form agents-wizard" onSubmit={onSubmit}>
      <h2>{editingId === null ? "Create agent" : `Edit agent ${editingId}`}</h2>

      <ol className="agents-wizard-steps" aria-label="Etapes">
        {STEPS.map((label, i) => (
          <li key={label}>
            <button
              type="button"
              className={i === step ? "wizard-step wizard-step-active" : "wizard-step"}
              aria-current={i === step ? "step" : undefined}
              onClick={() => setStep(i)}
            >
              {i + 1}. {label}
            </button>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <fieldset className="agents-step">
          <legend>Identite</legend>
          {editingId === null && (
            <div className="agents-form-row">
              <label htmlFor="agent-id">Id</label>
              <input
                id="agent-id"
                type="text"
                value={form.id}
                onChange={(e) => setField("id", e.target.value)}
                required
              />
            </div>
          )}
          <div className="agents-form-row">
            <label htmlFor="agent-runtime">Cible (en face)</label>
            <select
              id="agent-runtime"
              value={form.runtime}
              onChange={(e) => setField("runtime", e.target.value === "real" ? "real" : "lab")}
            >
              <option value="lab">Plateforme simulee (lab)</option>
              <option value="real">Serveur reel</option>
            </select>
          </div>
          <div className="agents-form-row">
            <label htmlFor="agent-ai-mode">IA derriere</label>
            <select
              id="agent-ai-mode"
              value={form.aiMode}
              onChange={(e) => setField("aiMode", e.target.value === "real" ? "real" : "mock")}
            >
              <option value="mock">Mock (scenario scripte)</option>
              <option value="real">IA reelle (ai_backend)</option>
            </select>
          </div>
          <div className="agents-form-row">
            <label htmlFor="agent-principal">Principal (identity)</label>
            <input
              id="agent-principal"
              type="text"
              value={form.principal}
              onChange={(e) => setField("principal", e.target.value)}
            />
          </div>
        </fieldset>
      )}

      {step === 1 && (
        <fieldset className="agents-step">
          <legend>Cible</legend>
          <div className="agents-form-row">
            <label htmlFor="agent-target-system">Target system (en face)</label>
            <select
              id="agent-target-system"
              value={form.targetSystem}
              onChange={(e) => setField("targetSystem", e.target.value)}
            >
              <option value="">(choisir un systeme)</option>
              {catalogSystems.map((sys) => (
                <option key={sys} value={sys}>
                  {sys}
                </option>
              ))}
            </select>
          </div>
          <div className="agents-form-row">
            <label htmlFor="agent-goal">Goal</label>
            <input
              id="agent-goal"
              type="text"
              value={form.goal}
              onChange={(e) => setField("goal", e.target.value)}
            />
          </div>
          <div className="agents-form-row">
            <label htmlFor="agent-pace-ms">Cadence (ms)</label>
            <input
              id="agent-pace-ms"
              type="number"
              min={0}
              step={100}
              value={form.pace_ms ?? ""}
              placeholder="herite du serveur / instant"
              onChange={(e) => {
                const raw = e.target.value.trim();
                const parsed = raw === "" ? undefined : Number.parseInt(raw, 10);
                setField(
                  "pace_ms",
                  parsed === undefined || Number.isNaN(parsed) ? undefined : Math.max(0, parsed),
                );
              }}
            />
          </div>
        </fieldset>
      )}

      {step === 2 && (
        <fieldset className="agents-step">
          <legend>IA</legend>
          <div className="agents-form-row">
            <label htmlFor="agent-role">Role</label>
            <input
              id="agent-role"
              type="text"
              value={form.role}
              placeholder="e.g. finance_admin"
              onChange={(e) => setField("role", e.target.value)}
            />
          </div>
          <div className="agents-form-row">
            <label htmlFor="agent-model">Model</label>
            <input
              id="agent-model"
              type="text"
              value={form.model}
              placeholder="e.g. llama-3.3-70b-versatile"
              onChange={(e) => setField("model", e.target.value)}
            />
          </div>
          <div className="agents-form-row">
            <label htmlFor="agent-system-prompt">System prompt</label>
            <textarea
              id="agent-system-prompt"
              rows={3}
              value={form.systemPrompt}
              placeholder="Instruction donnee a l'IA reelle (mode real)"
              onChange={(e) => setField("systemPrompt", e.target.value)}
            />
          </div>
          <div className="agents-form-row">
            <label htmlFor="agent-ai-backend">
              AI backend {form.aiMode === "real" ? "(requis)" : "(si IA reelle)"}
            </label>
            <select
              id="agent-ai-backend"
              value={form.aiBackendId}
              onChange={(e) => setField("aiBackendId", e.target.value)}
            >
              <option value="">(none)</option>
              {backends.map((backend) => (
                <option key={backend.id} value={backend.id}>
                  {backend.id} ({backend.provider} / {backend.model})
                </option>
              ))}
            </select>
          </div>
        </fieldset>
      )}

      {step === 3 && (
        <fieldset className="agents-step agents-actions-picker">
          <legend>
            Actions de l'agent (catalogue {form.targetSystem || "..."}) -- ce que l'agent fait
            {form.actions.length > 0 ? ` (${form.actions.length})` : ""}
          </legend>
          <p className="agents-backends-note">
            Coche les actions du catalogue du systeme cible. Elles definissent le scope ET le
            scenario mock (1 action = 1 etape, dans l'ordre coche).
          </p>
          {form.targetSystem === "" ? (
            <p className="agents-empty">Choisis d'abord un target system.</p>
          ) : scopedActions.length === 0 ? (
            <p className="agents-empty">Aucune action pour {form.targetSystem}.</p>
          ) : (
            scopedActions.map((a) => (
              <label key={a.action} className="agents-action-row">
                <input
                  type="checkbox"
                  checked={form.actions.includes(a.action)}
                  onChange={() => toggleAction(a.action)}
                />
                <code>{a.action}</code>
                <span className={`pill pill-${a.kind}`}>{a.kind}</span>
                <span className="agents-action-desc">{a.description}</span>
              </label>
            ))
          )}
          <div className="agents-form-row">
            <label htmlFor="agent-scenario">Scenario (JSON, avance)</label>
            <textarea
              id="agent-scenario"
              rows={5}
              value={form.scenarioJson}
              placeholder="Vide = genere depuis les actions cochees. Sinon un tableau JSON d'etapes."
              onChange={(e) => setField("scenarioJson", e.target.value)}
            />
          </div>
        </fieldset>
      )}

      {step === 4 && (
        <fieldset className="agents-step agents-actions-picker">
          <legend>Memoire (contexte borne)</legend>
          <label className="agents-action-row">
            <input
              type="checkbox"
              checked={form.memoryEnabled}
              onChange={(e) => setField("memoryEnabled", e.target.checked)}
            />
            Borner le contexte envoye au modele (fenetre glissante)
          </label>
          {form.memoryEnabled && (
            <div className="agents-form-row">
              <label htmlFor="agent-memory-window">Fenetre (messages)</label>
              <input
                id="agent-memory-window"
                type="number"
                min={1}
                value={form.memoryWindow ?? ""}
                placeholder="8"
                onChange={(e) => {
                  const n = Number.parseInt(e.target.value, 10);
                  setField("memoryWindow", Number.isFinite(n) && n >= 1 ? n : undefined);
                }}
              />
            </div>
          )}
        </fieldset>
      )}

      {step === 5 && (
        <AgentGroundTruthStep form={form} setField={setField} subjects={subjects} />
      )}

      {step === 6 && (
        <fieldset className="agents-step">
          <legend>Revue -- apercu avant {editingId === null ? "creation" : "sauvegarde"}</legend>
          {"error" in preview ? (
            <p className="agents-error-banner" role="alert">
              Scenario JSON invalide : {preview.error}
            </p>
          ) : (
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
                {preview.config.memory
                  ? `fenetre ${preview.config.memory.window}`
                  : "contexte complet"}
              </dd>
              <dt>ground-truth</dt>
              <dd>{preview.config.ground_truth ? "declare" : "(aucun)"}</dd>
            </dl>
          )}
        </fieldset>
      )}

      <div className="agents-form-actions">
        <button
          type="button"
          className="agents-btn"
          disabled={step === 0}
          onClick={() => setStep((s) => Math.max(0, s - 1))}
        >
          Precedent
        </button>
        {!isLast && (
          <button
            type="button"
            className="agents-btn"
            onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
          >
            Suivant
          </button>
        )}
        {isLast && (
          <button
            type="submit"
            className="agents-btn agents-btn-primary"
            disabled={"error" in preview}
          >
            {editingId === null ? "Create" : "Save"}
          </button>
        )}
        {editingId !== null && (
          <button type="button" className="agents-btn" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
