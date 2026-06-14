/**
 * AgentExplainModal -- explains a runtime agent (its config) in tabs: identity,
 * capabilities, scenario, and ground-truth.
 *
 * The recette tab resolves ground-truth from one of two disjoint sources, never
 * a guessed match: when the agent is mapped to a corpus subject via
 * corpus_subject_id, the subject's ground-truth fetched from GET /subjects/{id};
 * otherwise the agent's own inline ground_truth declared in its config (e.g. a
 * campaign probe). Only when neither exists is the tab empty.
 */
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getSubjectDetail } from "../api/client";
import type { SubjectDetail } from "../api/client";
import type { AgentConfig } from "../types/platform";
import TabbedModal from "./TabbedModal";
import type { Tab } from "./TabbedModal";
import { GroundTruthView, InlineGroundTruthView, KvList, RawJson, StringList } from "./explainViews";

interface Props {
  open: boolean;
  agent: AgentConfig | null;
  onClose: () => void;
}

function scenarioLines(agent: AgentConfig): string[] {
  return (agent.scenario ?? []).flatMap((step) => {
    if (step.kind !== "tool_call") return [];
    const args = (step.tool_args ?? {}) as Record<string, unknown>;
    return [`${String(step.tool_name)} -> ${String(args.resource ?? "")}`];
  });
}

/** Distinct tool names the scenario actually calls (what the agent attempts). */
function attemptedTools(agent: AgentConfig): string[] {
  const seen = new Set<string>();
  for (const step of agent.scenario ?? []) {
    if (step.kind === "tool_call") seen.add(String(step.tool_name));
  }
  return [...seen];
}

/**
 * Capabilities tab: the declared capability_scope, plus any tool the scenario
 * attempts that is NOT in scope -- the capability_overreach made legible. For an
 * empty-scope probe (camp-rogue-bot) the scope list is empty and every attempted
 * tool surfaces as out-of-scope, which is exactly the violation it tests.
 */
function capabilitiesTab(agent: AgentConfig): ReactNode {
  const scope = agent.capability_scope ?? [];
  const overreach = attemptedTools(agent).filter((tool) => !scope.includes(tool));
  return (
    <>
      <StringList items={scope} empty="Aucune action declaree (scope vide)." />
      {/* An empty scope is NOT an error: it is a deliberate state the operator
          should read, so spell out the two legitimate cases. */}
      {scope.length === 0 ? (
        <p className="tm-note">
          {overreach.length > 0 ? (
            <>
              Ce n&apos;est <strong>pas une erreur</strong> : un scope vide qui
              tente quand meme des actions est une <strong>sonde de
              depassement</strong> (capability_overreach). Les actions listees
              ci-dessous sortent du scope declare -- c&apos;est exactement la
              violation que ce sujet teste.
            </>
          ) : (
            <>
              Ce n&apos;est <strong>pas une erreur</strong> : un scope vide
              decrit un agent <strong>sans aucune capacite</strong> (non
              privilegie). Il ne declare le droit d&apos;executer aucune action ;
              toute action serait <strong>refusee par defaut</strong>
              (deny-by-default, fail-safe).
            </>
          )}
        </p>
      ) : null}
      {overreach.length > 0 ? (
        <>
          <h3>Actions tentees hors scope</h3>
          <ul className="tm-list">
            {overreach.map((tool) => (
              <li key={tool}>
                <strong>{tool}</strong> <span className="tm-pill tm-pill-bad">hors scope</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

function recetteTab(
  agent: AgentConfig,
  subject: SubjectDetail | null,
  loading: boolean,
  error: string | null,
): ReactNode {
  if (agent.corpus_subject_id === undefined || agent.corpus_subject_id === "") {
    const inline = agent.ground_truth;
    if (inline !== undefined && Object.keys(inline).length > 0) {
      return <InlineGroundTruthView groundTruth={inline as Record<string, unknown>} />;
    }
    return (
      <p className="tm-empty">
        Aucun ground-truth. Declare un bloc ground_truth inline sur la fiche agent, ou lie un
        sujet via le champ &quot;Sujet corpus&quot;, pour l&apos;afficher ici.
      </p>
    );
  }
  if (loading) return <p className="tm-empty">Chargement du sujet {agent.corpus_subject_id}...</p>;
  if (error !== null) return <p className="tm-empty">Erreur: {error}</p>;
  if (subject === null) return <p className="tm-empty">Sujet introuvable.</p>;
  return <GroundTruthView groundTruth={subject.ground_truth} />;
}

export default function AgentExplainModal({ open, agent, onClose }: Props): JSX.Element | null {
  const [subject, setSubject] = useState<SubjectDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const subjectId = agent?.corpus_subject_id ?? "";

  useEffect(() => {
    setSubject(null);
    setError(null);
    if (!open || subjectId === "") return;
    setLoading(true);
    let alive = true;
    void getSubjectDetail(subjectId)
      .then((d) => {
        if (alive) setSubject(d);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, subjectId]);

  if (!open || agent === null) return null;

  const tabs: Tab[] = [
    {
      key: "identity",
      label: "Identite",
      content: (
        <KvList
          entries={[
            ["Id", agent.id],
            ["Role", agent.role ?? ""],
            ["Principal", agent.principal ?? ""],
            ["Cible (target)", agent.target_system ?? ""],
            ["Runtime", agent.runtime],
            ["IA", agent.ai_mode ?? ""],
            ["AI backend", agent.ai_backend_id ?? ""],
            ["Model", agent.model ?? ""],
            ["Goal", agent.goal ?? ""],
            ["System prompt", agent.system_prompt ?? ""],
          ]}
        />
      ),
    },
    {
      key: "capabilities",
      label: "Capacites",
      content: capabilitiesTab(agent),
    },
    {
      key: "scenario",
      label: "Scenario",
      content: <StringList items={scenarioLines(agent)} empty="Aucun scenario scripte." />,
    },
    {
      key: "recette",
      label: "Recette",
      content: recetteTab(agent, subject, loading, error),
    },
    {
      key: "json",
      label: "JSON",
      content: <RawJson value={agent} />,
    },
  ];

  return <TabbedModal open={open} title={`Agent -- ${agent.id}`} tabs={tabs} onClose={onClose} />;
}
