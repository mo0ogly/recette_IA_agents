/**
 * Ground-truth step of the agent wizard: the optional inline expected verdict
 * over the four recette dimensions, plus the link to a corpus subject. Pure
 * presentation; state owned by the orchestrator via setField.
 */

import type { CorpusSubject } from "../../api/client";
import type { AgentFormValues } from "./agentForm";

interface AgentGroundTruthStepProps {
  form: AgentFormValues;
  setField: <K extends keyof AgentFormValues>(key: K, value: AgentFormValues[K]) => void;
  subjects: CorpusSubject[];
}

const DIMENSIONS: Array<[keyof AgentFormValues, string]> = [
  ["gtIdentityDim", "dimension identity OK"],
  ["gtCapabilitiesDim", "dimension capabilities OK"],
  ["gtPolicyDim", "dimension policy OK"],
  ["gtBehaviorDim", "dimension behavior OK"],
];

export default function AgentGroundTruthStep({
  form,
  setField,
  subjects,
}: AgentGroundTruthStepProps): JSX.Element {
  return (
    <fieldset className="agents-step agents-actions-picker">
      <legend>Ground-truth inline (verdict attendu sur les 4 dimensions)</legend>
      <div className="agents-form-row">
        <label htmlFor="agent-corpus-subject">Sujet corpus (ground-truth lie)</label>
        <select
          id="agent-corpus-subject"
          value={form.corpusSubjectId}
          onChange={(e) => setField("corpusSubjectId", e.target.value)}
        >
          <option value="">(aucun -- pas de ground-truth)</option>
          {subjects.map((s) => (
            <option key={s.agent_id} value={s.agent_id}>
              {s.agent_id} ({s.expected_verdict ?? "?"})
            </option>
          ))}
        </select>
      </div>
      <label className="agents-action-row">
        <input
          type="checkbox"
          checked={form.gtDetectable}
          onChange={(e) => setField("gtDetectable", e.target.checked)}
        />
        detectable
      </label>
      <div className="agents-form-row">
        <label htmlFor="agent-gt-verdict">Verdict attendu</label>
        <select
          id="agent-gt-verdict"
          value={form.gtVerdict}
          onChange={(e) => setField("gtVerdict", e.target.value as AgentFormValues["gtVerdict"])}
        >
          <option value="">(aucun)</option>
          <option value="correct">correct</option>
          <option value="incorrect">incorrect</option>
        </select>
      </div>
      <div className="agents-form-row">
        <label htmlFor="agent-gt-identity">Identite attendue</label>
        <input
          id="agent-gt-identity"
          type="text"
          value={form.gtIdentity}
          placeholder="e.g. bot@acme"
          onChange={(e) => setField("gtIdentity", e.target.value)}
        />
      </div>
      {DIMENSIONS.map(([key, label]) => (
        <label key={key} className="agents-action-row">
          <input
            type="checkbox"
            checked={form[key] as boolean}
            onChange={(e) => setField(key, e.target.checked as never)}
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}
