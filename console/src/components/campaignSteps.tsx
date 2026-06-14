/**
 * Multi-agent breakdown of a CAMPAIGN run. A campaign chains several agents as
 * ordered steps (campaign.steps); this folds the run's frames into one entry per
 * step -- the acting agent, its actions, its outcome -- so the campaign eye shows
 * the run per agent instead of collapsing it to one. Pure + side-effect free so
 * it is unit-testable (groupSteps) and reusable by AgentRunModal's Etapes tab.
 *
 * Frame order (recette/api/runners.py campaign runner): agent_start -> step* ->
 * agent_done (or step_error) per step, then campaign_done / end.
 */

import type { RunEvent } from "../types/platform";
import "./campaignSteps.css";

export interface CampaignStepRef {
  agent_id: string;
}

type StepStatus = "pending" | "running" | "done" | "error";

export interface StepEntry {
  index: number;
  agentId: string;
  provider: string | null;
  actions: string[];
  status: StepStatus;
  message: string | null;
  recordingId: string | null;
  actionCount: number | null;
}

function frameSeq(frame: RunEvent): number | null {
  const seq = (frame as { seq?: unknown }).seq;
  return typeof seq === "number" ? seq : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

/** Render a single `step` frame's executed action as a readable line. */
function actionLine(data: Record<string, unknown>): string {
  const action = asRecord(data.action);
  if (Object.keys(action).length === 0) {
    return "etape sans action externe";
  }
  const type = String(action.action_type ?? "?");
  const target = String(action.target_system ?? "?");
  const resource = action.resource ? `/${String(action.resource)}` : "";
  const mode = action.mode ? ` [${String(action.mode)}]` : "";
  return `${type} -> ${target}${resource}${mode}`;
}

/**
 * Fold ordered frames into one entry per campaign step. Steps run sequentially,
 * so a `step` frame belongs to the last opened step. A step_error may arrive
 * with no preceding agent_start (e.g. unknown agent), so it opens its own entry.
 * With no frames yet, the declared steps are returned as "pending" so the plan
 * is visible before a run.
 */
export function groupSteps(
  frames: RunEvent[],
  declared: CampaignStepRef[],
): StepEntry[] {
  const ordered = [...frames].sort((a, b) => (frameSeq(a) ?? 0) - (frameSeq(b) ?? 0));
  const entries: StepEntry[] = [];
  let current: StepEntry | null = null;
  for (const frame of ordered) {
    const data = asRecord((frame as { data?: unknown }).data);
    const idx = typeof data.index === "number" ? data.index : entries.length;
    switch (frame.type) {
      case "agent_start": {
        current = {
          index: idx,
          agentId: String(data.agent_id ?? ""),
          provider: data.provider ? String(data.provider) : null,
          actions: [],
          status: "running",
          message: null,
          recordingId: null,
          actionCount: null,
        };
        entries.push(current);
        break;
      }
      case "step": {
        if (current !== null) {
          current.actions.push(actionLine(data));
        }
        break;
      }
      case "agent_done": {
        if (current !== null) {
          current.status = "done";
          current.recordingId = data.recording_id ? String(data.recording_id) : null;
          current.actionCount =
            typeof data.actions === "number" ? data.actions : current.actions.length;
        }
        break;
      }
      case "step_error": {
        if (current?.index === idx) {
          current.status = "error";
          current.message = String(data.message ?? "erreur");
        } else {
          entries.push({
            index: idx,
            agentId: String(data.agent_id ?? ""),
            provider: null,
            actions: [],
            status: "error",
            message: String(data.message ?? "erreur"),
            recordingId: null,
            actionCount: null,
          });
        }
        current = null;
        break;
      }
      default:
        break;
    }
  }
  if (entries.length === 0) {
    return declared.map((s, i) => ({
      index: i,
      agentId: s.agent_id,
      provider: null,
      actions: [],
      status: "pending" as StepStatus,
      message: null,
      recordingId: null,
      actionCount: null,
    }));
  }
  return entries;
}

const STEP_LABEL: Record<StepStatus, string> = {
  pending: "pas lance",
  running: "en cours",
  done: "termine",
  error: "erreur",
};

/** The per-step list view of a campaign run (used in the Etapes tab). */
export function CampaignStepsView(props: {
  entries: StepEntry[];
  runId: string | null;
}): JSX.Element {
  const { entries, runId } = props;
  if (entries.length === 0) {
    return <p className="run-empty">Cette campagne n&apos;a aucune etape.</p>;
  }
  return (
    <>
      {runId === null ? (
        <p className="camp-steps-note">
          Campagne jamais lancee -- etapes declarees, dans l&apos;ordre.
        </p>
      ) : null}
      <ol className="camp-steps">
        {entries.map((e) => (
          <li key={`${e.index}-${e.agentId}`} className="camp-step">
            <div className="camp-step-head">
              <span className="camp-step-idx">#{e.index + 1}</span>
              <strong>{e.agentId}</strong>
              {e.provider ? <span className="camp-step-prov">{e.provider}</span> : null}
              <span
                className={`tm-pill ${
                  e.status === "error" ? "tm-pill-bad" : e.status === "done" ? "tm-pill-ok" : ""
                }`}
              >
                {STEP_LABEL[e.status]}
              </span>
            </div>
            {e.message ? <div className="camp-step-err">{e.message}</div> : null}
            {e.actions.length > 0 ? (
              <ul className="camp-step-actions">
                {e.actions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            ) : e.status === "done" ? (
              <div className="camp-step-actions-empty">Aucune action externe.</div>
            ) : null}
            {e.recordingId ? (
              <div className="camp-step-rec">
                enregistrement <code>{e.recordingId}</code>
                {e.actionCount !== null ? ` -- ${e.actionCount} action(s)` : ""}
              </div>
            ) : null}
          </li>
        ))}
      </ol>
    </>
  );
}
