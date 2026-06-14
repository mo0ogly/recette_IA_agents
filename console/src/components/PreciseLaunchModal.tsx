/**
 * PreciseLaunchModal -- launch one agent as a precise scripted *instance*.
 *
 * The operator picks a subset of the target system's actions (pre-checked =
 * the agent's capability_scope), a resource per action, a profile and a
 * repetition count. We build a deterministic Lane B scenario (I4) and launch it
 * via launchLaneB({agent_id, stub_script}); the run streams through
 * useRunStream and we judge the frames inline (capability + policy).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { launchLaneB, listAgentActions } from "../api/client";
import { useRunStream } from "../hooks/useRunStream";
import type { AgentAction, AgentConfig } from "../types/platform";
import {
  buildScenario,
  defaultResource,
  judgeInstance,
  type PickedAction,
  type Profile,
} from "../pages/dashboard/instanceModel";
import "./PreciseLaunchModal.css";

interface Props {
  open: boolean;
  agent: AgentConfig | null;
  onClose: () => void;
}

const PROFILES: Profile[] = ["legit", "suspect", "destructif"];

export default function PreciseLaunchModal({ open, agent, onClose }: Props): JSX.Element | null {
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [resources, setResources] = useState<Record<string, string>>({});
  const [profile, setProfile] = useState<Profile>("legit");
  const [repeat, setRepeat] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [launched, setLaunched] = useState(false);
  const stream = useRunStream();
  const { start: streamStart } = stream;

  const scope = useMemo(() => agent?.capability_scope ?? [], [agent]);

  useEffect(() => {
    if (!open || agent === null) return;
    setError(null);
    setChecked(new Set(scope));
    // Pre-fill the pre-checked (capability_scope) actions with recette-realistic
    // resources so no field ships empty; the operator can still override.
    setResources(
      Object.fromEntries(scope.map((a) => [a, defaultResource(a, agent.target_system ?? "")])),
    );
    setProfile("legit");
    setRepeat(1);
    setLaunched(false);
    void listAgentActions()
      .then((all) => setActions(all.filter((a) => a.target_system === agent.target_system)))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [open, agent, scope]);

  const toggle = (name: string): void => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
    // Seed a default resource the first time an action is checked.
    setResources((prev) =>
      prev[name] !== undefined || agent === null
        ? prev
        : { ...prev, [name]: defaultResource(name, agent.target_system ?? "") },
    );
  };

  const launch = useCallback(async () => {
    if (agent === null) return;
    const picks: PickedAction[] = [...checked].map((tool_name) => ({
      tool_name,
      resource: (resources[tool_name] ?? "").trim(),
    }));
    if (picks.length === 0) {
      setError("Coche au moins une action.");
      return;
    }
    const missing = picks.find((p) => p.resource === "");
    if (missing) {
      setError(`Donne une ressource pour ${missing.tool_name}.`);
      return;
    }
    setError(null);
    setLaunched(true);
    const scenario = buildScenario(picks, repeat);
    await streamStart(() => launchLaneB({ agent_id: agent.id, stub_script: scenario }));
  }, [agent, checked, resources, repeat, streamStart]);

  const verdicts = useMemo(() => {
    if (agent === null || stream.frames.length === 0) return [];
    return judgeInstance(
      { profile, pickedActions: [...checked], capabilityScope: scope },
      stream.frames,
    );
  }, [agent, profile, checked, scope, stream.frames]);

  const done = launched && stream.status !== "" && !stream.running && stream.frames.length > 0;

  if (!open || agent === null) return null;

  return (
    <div className="pl-backdrop" role="dialog" aria-modal="true" aria-label="Lancer une instance precise">
      <div className="pl-modal">
        <div className="pl-head">
          <h2>Instance precise -- {agent.id}</h2>
          <button type="button" className="pl-close" onClick={onClose} aria-label="Fermer">
            {"×"}
          </button>
        </div>

        {error !== null && (
          <div className="pl-error" role="alert">
            {error}
          </div>
        )}

        {stream.error !== null && (
          <div className="pl-error" role="alert">
            {stream.error}
          </div>
        )}

        <fieldset className="pl-actions">
          <legend>Actions ({agent.target_system}) -- cochees = capability_scope</legend>
          {actions.length === 0 && <p className="pl-muted">Aucune action pour ce systeme.</p>}
          {actions.map((a) => {
            const isChecked = checked.has(a.action);
            const inScope = scope.includes(a.action);
            return (
              <div key={a.action} className="pl-action-row">
                <label className="pl-action-label">
                  <input type="checkbox" checked={isChecked} onChange={() => toggle(a.action)} />
                  {a.action}
                  {!inScope && <span className="pl-badge-out">hors-scope</span>}
                </label>
                {isChecked && (
                  <input
                    className="pl-resource"
                    aria-label={`ressource pour ${a.action}`}
                    placeholder="ressource (ex: acme/widgets)"
                    value={resources[a.action] ?? ""}
                    onChange={(e) =>
                      setResources((prev) => ({ ...prev, [a.action]: e.target.value }))
                    }
                  />
                )}
              </div>
            );
          })}
        </fieldset>

        <div className="pl-params">
          <label className="pl-field">
            <span>Profil attendu</span>
            <select value={profile} onChange={(e) => setProfile(e.target.value as Profile)}>
              {PROFILES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="pl-field">
            <span>Repetition</span>
            <input
              type="number"
              min={1}
              value={repeat}
              onChange={(e) => setRepeat(Number(e.target.value) || 1)}
            />
          </label>
        </div>

        <div className="pl-foot">
          <button type="button" className="btn-primary" disabled={stream.running} onClick={() => void launch()}>
            {stream.running ? "Lancement..." : "Lancer l'instance"}
          </button>
          {stream.runId !== null && (
            <span className="pl-status">
              run {stream.runId} -- {stream.status}
            </span>
          )}
        </div>

        {done && (
          <div className="pl-verdicts" data-testid="pl-verdicts">
            {verdicts.map((v) => (
              <div key={v.dimension} className={`pl-verdict pl-${v.pass ? "pass" : "fail"}`}>
                <span className="pl-dim">{v.dimension}</span>
                <span className="pl-chip">{v.pass ? "PASS" : "FAIL"}</span>
                <span className="pl-reason">{v.reason}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
