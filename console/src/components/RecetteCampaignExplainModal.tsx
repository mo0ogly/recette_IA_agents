/**
 * RecetteCampaignExplainModal -- explains an on-disk recette governance campaign
 * in tabs: objective/teaching, the scored actions (each with its expected
 * verdict), the seeded agents, and the raw JSON. Source: GET
 * /recette-campaigns/{id}.
 *
 * Mirrors AgentExplainModal / SubjectExplainModal so every catalog row has the
 * same "Expliquer" eye + modal (UI coherence; no backend artifact without a UI).
 * Read-only: this never runs or mutates the campaign (the CRUD campaigns live
 * on the /campaigns page).
 */
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getRecetteCampaign } from "../api/client";
import type {
  PolicyVerdict,
  RecetteCampaignAction,
  RecetteCampaignDetail,
  RecetteCampaignLink,
} from "../types/platform";
import TabbedModal from "./TabbedModal";
import type { Tab } from "./TabbedModal";
import { KvList, RawJson } from "./explainViews";

interface Props {
  open: boolean;
  campaignId: string | null;
  onClose: () => void;
}

/** Map an expected verdict to a pill tone (allow=ok, deny=bad, escalate=neutral). */
function verdictPillClass(expect: PolicyVerdict | undefined): string {
  if (expect === "allow") return "tm-pill tm-pill-ok";
  if (expect === "deny") return "tm-pill tm-pill-bad";
  return "tm-pill"; // escalate or unset -> neutral
}

function actionsTab(actions: RecetteCampaignAction[]): ReactNode {
  if (actions.length === 0) return <p className="tm-empty">Aucune action.</p>;
  return (
    <ol className="tm-list rc-actions" data-testid="rc-actions">
      {actions.map((a, i) => (
        <li key={`${a.action_type}-${a.resource}-${i}`} className="rc-action">
          <div className="rc-action-head">
            <strong>{a.action_type}</strong>
            <span className="rc-action-target">
              {"->"} {a.target_system}/{a.resource}
            </span>
            <span className={verdictPillClass(a.expect)}>{a.expect ?? "(non specifie)"}</span>
          </div>
          {a.rationale !== undefined && a.rationale !== "" ? (
            <p className="rc-action-rationale">{a.rationale}</p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/**
 * Orchestration tab: present only on a macro orchestration campaign (a campaign
 * with a `links` block). It makes the team <-> campaign agreement legible: the
 * MAF team this campaign is bound to, the shared action both sides gate, and the
 * invariant (I6) they agree on. The team plans the approval gate; the gateway
 * enforces it -- this tab is where a reader sees that, not a hidden script.
 */
function orchestrationTab(links: RecetteCampaignLink[]): ReactNode {
  return (
    <div data-testid="rc-links">
      <p className="tm-note">
        Macro-campagne d&apos;orchestration : cette campagne gouvernee est{" "}
        <strong>liee a un team MAF</strong>. Les deux s&apos;accordent sur la barriere
        humaine -- le team declare l&apos;approbation sur son outil, la gateway{" "}
        <strong>escalade</strong> la meme action (I6).
      </p>
      <ul className="tm-list">
        {links.map((link, i) => (
          <li key={`${link.team}-${i}`} className="rc-link">
            <div className="rc-link-head">
              <strong>{link.team}</strong>
              <span className="tm-pill">{link.shared_action}</span>
              {link.invariant !== undefined && link.invariant !== "" ? (
                <span className="tm-pill tm-pill-ok">{link.invariant}</span>
              ) : null}
            </div>
            {link.note !== undefined && link.note !== "" ? (
              <p className="rc-action-rationale">{link.note}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function objectiveTab(detail: RecetteCampaignDetail): ReactNode {
  return (
    <>
      <KvList
        entries={[
          ["Nom", detail.name],
          ["Famille", detail.family],
          ["Objectif", detail.objective ?? ""],
          ["Pedagogie", detail.teaching ?? ""],
        ]}
      />
      {detail.objective === undefined && detail.teaching === undefined ? (
        <p className="tm-empty">Pas d&apos;objectif ni de pedagogie declares.</p>
      ) : null}
    </>
  );
}

export default function RecetteCampaignExplainModal({
  open,
  campaignId,
  onClose,
}: Props): JSX.Element | null {
  const [detail, setDetail] = useState<RecetteCampaignDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    if (!open || campaignId === null) return;
    setLoading(true);
    let alive = true;
    void getRecetteCampaign(campaignId)
      .then((d) => {
        if (alive) setDetail(d);
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
  }, [open, campaignId]);

  if (!open || campaignId === null) return null;

  if (loading || error !== null || detail === null) {
    const note = loading ? `Chargement de ${campaignId}...` : (error ?? "Campagne introuvable.");
    const tabs: Tab[] = [{ key: "state", label: "Campagne", content: <p className="tm-empty">{note}</p> }];
    return <TabbedModal open={open} title={`Campagne recette -- ${campaignId}`} tabs={tabs} onClose={onClose} />;
  }

  const tabs: Tab[] = [
    { key: "objective", label: "Objectif", content: objectiveTab(detail) },
    {
      key: "actions",
      label: `Actions (${detail.actions.length})`,
      content: actionsTab(detail.actions),
    },
    {
      key: "agents",
      label: `Agents (${detail.agents.length})`,
      content: (
        <KvList entries={detail.agents.map((a) => [a.id, `${a.runtime}`] as [string, string])} />
      ),
    },
    { key: "json", label: "JSON", content: <RawJson value={detail} /> },
  ];

  // A macro orchestration campaign gets an extra tab making its MAF-team link legible.
  if (detail.links !== undefined && detail.links.length > 0) {
    tabs.splice(1, 0, {
      key: "orchestration",
      label: "Orchestration",
      content: orchestrationTab(detail.links),
    });
  }

  return (
    <TabbedModal open={open} title={`Campagne recette -- ${detail.name}`} tabs={tabs} onClose={onClose} />
  );
}
