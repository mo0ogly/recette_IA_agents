/**
 * Pure form logic for the Agents page: the editable form shape and the
 * lossless conversions between it and the AgentConfig wire shape. No React,
 * no side effects -- fully unit-testable in isolation.
 */

import type { AgentConfig } from "../../types/platform";

/** Form state: every field as the raw string the user types. */
export interface AgentFormValues {
  id: string;
  runtime: "lab" | "real";
  aiMode: "mock" | "real";
  principal: string;
  targetSystem: string;
  goal: string;
  actions: string[];
  aiBackendId: string;
  corpusSubjectId: string;
  /** Per-agent cadence in ms; undefined = inherit from server / instant. */
  pace_ms?: number;
  // Full properties (previously invisible in the form).
  role: string;
  model: string;
  systemPrompt: string;
  scenarioJson: string;
  /** Bounded-memory: cap the conversation context fed to the model. */
  memoryEnabled: boolean;
  memoryWindow?: number;
  gtDetectable: boolean;
  gtVerdict: "" | "correct" | "incorrect";
  gtIdentity: string;
  gtIdentityDim: boolean;
  gtCapabilitiesDim: boolean;
  gtPolicyDim: boolean;
  gtBehaviorDim: boolean;
}

export const EMPTY_FORM: AgentFormValues = {
  id: "",
  runtime: "lab",
  aiMode: "mock",
  principal: "",
  targetSystem: "",
  goal: "",
  actions: [],
  aiBackendId: "",
  corpusSubjectId: "",
  role: "",
  model: "",
  systemPrompt: "",
  scenarioJson: "",
  memoryEnabled: false,
  memoryWindow: undefined,
  gtDetectable: false,
  gtVerdict: "",
  gtIdentity: "",
  gtIdentityDim: false,
  gtCapabilitiesDim: false,
  gtPolicyDim: false,
  gtBehaviorDim: false,
};

/** Turn a list of chosen catalog actions into a deterministic mock scenario
 *  (one tool_call per action, then a final step). */
export function scenarioFromActions(actions: string[]): Array<Record<string, unknown>> {
  const steps: Array<Record<string, unknown>> = actions.map((action) => ({
    kind: "tool_call",
    tool_name: action,
    tool_args: { resource: "acme/x" },
  }));
  steps.push({ kind: "final", text: "done" });
  return steps;
}

/** Build the optional ground_truth block from the inline form fields, or
 *  undefined when nothing is declared. */
export function groundTruthFrom(values: AgentFormValues): AgentConfig["ground_truth"] {
  const anyDim =
    values.gtIdentityDim ||
    values.gtCapabilitiesDim ||
    values.gtPolicyDim ||
    values.gtBehaviorDim;
  if (
    !values.gtDetectable &&
    values.gtVerdict === "" &&
    values.gtIdentity.trim() === "" &&
    !anyDim
  ) {
    return undefined;
  }
  return {
    detectable: values.gtDetectable,
    expected_verdict: values.gtVerdict === "" ? undefined : values.gtVerdict,
    expected_identity: values.gtIdentity.trim() || undefined,
    dimensions: {
      identity: values.gtIdentityDim,
      capabilities: values.gtCapabilitiesDim,
      policy: values.gtPolicyDim,
      behavior: values.gtBehaviorDim,
    },
  };
}

/** Convert the form into an AgentConfig payload for create/update.
 *
 *  A raw scenario JSON (if valid) wins over the action-derived mock scenario,
 *  so a custom multi-step scenario is preserved through an edit. */
export function toAgentConfig(values: AgentFormValues, id: string): AgentConfig {
  let scenario = scenarioFromActions(values.actions);
  const raw = values.scenarioJson.trim();
  if (raw !== "") {
    const parsed: unknown = JSON.parse(raw); // throws -> caught by the caller
    if (!Array.isArray(parsed)) {
      throw new Error("scenario must be a JSON array");
    }
    scenario = parsed as Array<Record<string, unknown>>;
  }
  return {
    id,
    runtime: values.runtime,
    ai_mode: values.aiMode,
    principal: values.principal.trim() || undefined,
    target_system: values.targetSystem.trim() || undefined,
    goal: values.goal.trim() || undefined,
    capability_scope: values.actions,
    pace_ms: values.pace_ms,
    scenario,
    ai_backend_id: values.aiBackendId || undefined,
    corpus_subject_id: values.corpusSubjectId || undefined,
    role: values.role.trim() || undefined,
    model: values.model.trim() || undefined,
    system_prompt: values.systemPrompt.trim() || undefined,
    memory: values.memoryEnabled
      ? { enabled: true, window: values.memoryWindow ?? 8 }
      : undefined,
    ground_truth: groundTruthFrom(values),
  };
}

/** Load an existing agent into the form for editing. */
export function toFormValues(agent: AgentConfig): AgentFormValues {
  const gt = agent.ground_truth ?? {};
  const dims = gt.dimensions ?? {};
  return {
    id: agent.id,
    runtime: agent.runtime,
    aiMode: agent.ai_mode ?? (agent.ai_backend_id ? "real" : "mock"),
    principal: agent.principal ?? "",
    targetSystem: agent.target_system ?? "",
    goal: agent.goal ?? "",
    actions: agent.capability_scope ?? [],
    pace_ms: agent.pace_ms,
    aiBackendId: agent.ai_backend_id ?? "",
    corpusSubjectId: agent.corpus_subject_id ?? "",
    role: agent.role ?? "",
    model: agent.model ?? "",
    systemPrompt: agent.system_prompt ?? "",
    scenarioJson: agent.scenario ? JSON.stringify(agent.scenario, null, 2) : "",
    memoryEnabled: agent.memory?.enabled ?? false,
    memoryWindow: agent.memory?.window,
    gtDetectable: gt.detectable ?? false,
    gtVerdict: gt.expected_verdict ?? "",
    gtIdentity: gt.expected_identity ?? "",
    gtIdentityDim: dims.identity ?? false,
    gtCapabilitiesDim: dims.capabilities ?? false,
    gtPolicyDim: dims.policy ?? false,
    gtBehaviorDim: dims.behavior ?? false,
  };
}

/** Normalize an unknown error into a message string. */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
