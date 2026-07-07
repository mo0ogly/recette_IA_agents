/**
 * Campaigns page -- persisted, on-demand discovery-recette campaigns.
 *
 * A campaign is an ordered set of agent launches. Each agent already carries
 * its own actions (its scenario, composed from the action catalog on the
 * Agents tab); a campaign just selects which agents run, in order. Running one
 * streams live frames into the run console and persists one recording per step;
 * a recording can be replayed deterministically (I4).
 *
 * The screen is split into four tabs (the single stacked view was too dense):
 *   - Modeles par domaine : the templates, grouped by ACTIVITY DOMAIN
 *     (target_system -> business area), each domain exposing its situations
 *     (legit / suspect / destructif). One click builds a "full-spectrum"
 *     campaign that chains every situation of a domain in escalating order.
 *   - Campagnes           : the persisted campaigns, run / delete.
 *   - Enregistrements     : recordings + deterministic replay (I4).
 *   - Creer               : the manual campaign builder.
 * The run console stays mounted below the tabs so a launch is visible from any
 * tab.
 *
 * Status per campaign is polled from GET /runs (matched on campaign_id).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createCampaign,
  deleteCampaign,
  instantiateTemplate,
  listAgents,
  listCampaigns,
  listCampaignTemplates,
  listRecordings,
  listRuns,
  replayRecording,
  runCampaign,
} from "../../api/client";
import { useRunStream } from "../../hooks/useRunStream";
import type { RunFrame } from "../../hooks/useRunStream";
import type {
  AgentConfig,
  Campaign,
  CampaignTemplate,
  RecordingMeta,
  RunSummary,
} from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import { LogConsole } from "../../components/LogConsole";
import type { LogLine } from "../../components/LogConsole";
import AgentRunModal from "../../components/AgentRunModal";
import EyeIcon from "../../components/EyeIcon";
import "./campaigns.css";

const POLL_MS = 2000;
const ACTIVE = new Set(["pending", "running"]);

type TabKey = "templates" | "campaigns" | "recordings" | "create";

const TABS: ReadonlyArray<{ key: TabKey; label: string }> = [
  { key: "templates", label: "Modeles par domaine" },
  { key: "campaigns", label: "Campagnes" },
  { key: "recordings", label: "Enregistrements" },
  { key: "create", label: "Creer" },
];

/** Activity-domain labels keyed by the agent target_system. A campaign groups
 *  situations within one business area so the recette team reasons per domaine,
 *  not per opaque system id. */
const DOMAIN_LABELS: Record<string, string> = {
  okta: "Identite & Acces (IAM)",
  github: "Code & CI/CD",
  finance: "Finance",
  crm: "Relation client (CRM)",
  slack: "Collaboration",
  cloud: "Infrastructure Cloud",
  data_platform: "Donnees & Analytics",
  hris: "Ressources humaines",
  support_desk: "Support client",
  legal_dms: "Juridique",
  product_cms: "Produit",
};

/** Escalating order of situations for a full-spectrum domain campaign:
 *  nominal first, then overreach, then irreversible. */
const PROFILE_ORDER: Record<string, number> = {
  legit: 0,
  suspect: 1,
  destructive: 2,
};

function domainLabel(system: string): string {
  return DOMAIN_LABELS[system] ?? system;
}

function frameLine(f: RunFrame): string {
  const d = f.data;
  const agent = d.agent_id ? ` ${String(d.agent_id)}` : "";
  switch (f.type) {
    case "start":
      return "run start";
    case "agent_start":
      return `agent_start${agent} (${String(d.provider ?? "")})`;
    case "step":
      return `step${agent} #${String(d.index ?? "")}`;
    case "agent_done":
      return `agent_done${agent} -> ${String(d.actions ?? 0)} actions, rec=${String(d.recording_id ?? "")}`;
    case "campaign_done":
      return `campaign_done (${String(d.steps ?? 0)} steps)`;
    case "step_error":
      return `step_error${agent}: ${String(d.message ?? "")}`;
    case "replay_result":
      return `replay_result: matches_original=${String(d.matches_original)}`;
    case "error":
      return `error: ${String(d.message ?? "")}`;
    case "end":
      return `end (${String(d.status ?? "")})`;
    default:
      return f.type;
  }
}

/** Map one streamed campaign frame to a displayable log line.
 *  Step failures (step_error) and run failures (error) are error-level. */
function frameToLogLine(f: RunFrame): LogLine {
  return {
    seq: f.seq,
    level: f.type === "step_error" || f.type === "error" ? "error" : "info",
    source: typeof f.data.agent_id === "string" ? f.data.agent_id : "run",
    text: frameLine(f),
  };
}

interface DomainGroup {
  system: string;
  label: string;
  templates: CampaignTemplate[];
}

/** Group templates by activity domain, sorting domains alphabetically by label
 *  and situations by escalating profile order (deterministic, stable view). */
function groupByDomain(templates: CampaignTemplate[]): DomainGroup[] {
  const bySystem = new Map<string, CampaignTemplate[]>();
  for (const t of templates) {
    const list = bySystem.get(t.target_system) ?? [];
    list.push(t);
    bySystem.set(t.target_system, list);
  }
  const groups: DomainGroup[] = [];
  for (const [system, list] of bySystem) {
    const sorted = [...list].sort(
      (a, b) => (PROFILE_ORDER[a.profile] ?? 9) - (PROFILE_ORDER[b.profile] ?? 9),
    );
    groups.push({ system, label: domainLabel(system), templates: sorted });
  }
  groups.sort((a, b) => a.label.localeCompare(b.label));
  return groups;
}

export default function CampaignsPage(): JSX.Element {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [recordings, setRecordings] = useState<RecordingMeta[]>([]);
  const [templates, setTemplates] = useState<CampaignTemplate[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("templates");

  // The campaign whose run is open in the eye modal (its latest run, per step).
  const [viewing, setViewing] = useState<{
    campaign: Campaign;
    runId: string | null;
    status: string;
  } | null>(null);

  const [newId, setNewId] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const stream = useRunStream();
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [c, a, r, t] = await Promise.all([
        listCampaigns(),
        listAgents(),
        listRecordings(),
        listCampaignTemplates(),
      ]);
      setCampaigns(c);
      setAgents(a);
      setRecordings(r);
      setTemplates(t);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      setRuns(await listRuns());
    } catch {
      // transient
    }
  }, []);

  useEffect(() => {
    void refresh();
    void poll();
    timer.current = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      if (timer.current !== null) {
        window.clearInterval(timer.current);
      }
    };
  }, [refresh, poll]);

  const domains = useMemo(() => groupByDomain(templates), [templates]);

  const runFor = (campaignId: string): RunSummary | undefined =>
    runs.find((r) => r.campaign_id === campaignId);

  const togglePick = (id: string): void => {
    setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const create = useCallback(async () => {
    const id = newId.trim();
    if (id === "" || picked.length === 0) {
      setError("Donne un id de campagne et coche au moins un agent.");
      return;
    }
    try {
      await createCampaign({
        id,
        description: newDesc.trim(),
        steps: picked.map((agentId) => ({ agent_id: agentId })),
      });
      setNewId("");
      setNewDesc("");
      setPicked([]);
      await refresh();
      setTab("campaigns");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [newId, newDesc, picked, refresh]);

  const instantiate = useCallback(
    async (id: string) => {
      try {
        await instantiateTemplate(id);
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refresh],
  );

  /** Build a full-spectrum campaign for one activity domain: instantiate every
   *  missing template of the domain, then create a single campaign chaining
   *  their agents in escalating order (legit -> suspect -> destructif). Uses
   *  only existing endpoints; no campaign is created if the domain is empty. */
  const createDomainCampaign = useCallback(
    async (group: DomainGroup) => {
      if (group.templates.length === 0) {
        return;
      }
      try {
        for (const t of group.templates) {
          if (!campaigns.some((c) => c.id === t.id)) {
            await instantiateTemplate(t.id);
          }
        }
        const situations = group.templates.map((t) => t.profile).join(" -> ");
        await createCampaign({
          id: `domaine-${group.system}-spectre`,
          description: `Spectre complet ${group.label} : ${situations}`,
          steps: group.templates.map((t) => ({ agent_id: t.agent_id })),
        });
        await refresh();
        setTab("campaigns");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [campaigns, refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      if (!window.confirm(`Supprimer la campagne "${id}" ?`)) {
        return;
      }
      try {
        await deleteCampaign(id);
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [refresh],
  );

  const run = useCallback(
    async (id: string) => {
      await stream.start(() => runCampaign(id));
      window.setTimeout(() => void Promise.all([refresh(), poll()]), 1500);
    },
    [stream, refresh, poll],
  );

  const replay = useCallback(
    async (recordingId: string) => {
      await stream.start(() => replayRecording(recordingId));
    },
    [stream],
  );

  const replayResult = stream.frames.find((f) => f.type === "replay_result");

  return (
    <div>
      <div className="page-head">
        <h1>Campagnes</h1>
        <PageHelp topic="campaigns" />
        <AssistButton topic="campaigns.list" label="Catalogue des campagnes" />
      </div>

      {error !== null && (
        <div className="camp-error" role="alert">
          {error}
        </div>
      )}

      <div className="run-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={tab === t.key ? "run-tab run-tab-active" : "run-tab"}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "templates" && (
        <section className="panel camp-templates" role="tabpanel">
          <h2>Modeles par domaine d'activite</h2>
          <p className="camp-desc">
            Chaque domaine metier expose ses situations. Profil : legit
            (autorise), suspect (depassement), destructif (irreversible).{" "}
            <strong>Creer la campagne domaine</strong> enchaine toutes les
            situations du domaine, dans l'ordre legit -&gt; suspect -&gt;
            destructif, pour une recette "spectre complet" en un clic.
          </p>
          {domains.length === 0 ? (
            <p className="camp-empty">Aucun modele disponible.</p>
          ) : (
            domains.map((group) => (
              <div key={group.system} className="camp-domain">
                <div className="camp-domain-head">
                  <h3 className="camp-domain-title">
                    {group.label}{" "}
                    <span className="camp-mono camp-desc">{group.system}</span>
                  </h3>
                  <button
                    type="button"
                    onClick={() => void createDomainCampaign(group)}
                  >
                    Creer la campagne domaine ({group.templates.length} situations)
                  </button>
                </div>
                <table className="camp-table">
                  <thead>
                    <tr>
                      <th>Campagne</th>
                      <th>Situation</th>
                      <th>Actions</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.templates.map((t) => {
                      const exists = campaigns.some((c) => c.id === t.id);
                      return (
                        <tr key={t.id}>
                          <td>
                            <strong>{t.title}</strong>
                            <div className="camp-mono camp-desc">{t.id}</div>
                          </td>
                          <td>
                            <span className={`pill pill-profile-${t.profile}`}>
                              {t.profile}
                            </span>
                          </td>
                          <td className="camp-mono">{t.actions.join(", ")}</td>
                          <td>
                            <button
                              type="button"
                              onClick={() => void instantiate(t.id)}
                              disabled={exists}
                            >
                              {exists ? "Instancie" : "Instancier"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ))
          )}
        </section>
      )}

      {tab === "campaigns" && (
        <section className="panel" role="tabpanel">
          <h2>Campagnes</h2>
          {campaigns.length === 0 ? (
            <p className="camp-empty">
              Aucune campagne. Cree-en une depuis l'onglet Modeles ou Creer.
            </p>
          ) : (
            <table className="camp-table">
              <thead>
                <tr>
                  <th>Id</th>
                  <th>Agents (etapes)</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => {
                  const latestRun = runFor(c.id);
                  const st = latestRun?.status ?? "";
                  const active = ACTIVE.has(st);
                  return (
                    <tr key={c.id}>
                      <td>
                        <strong>{c.id}</strong>
                        <div className="camp-desc">{c.description}</div>
                      </td>
                      <td className="camp-mono">
                        {c.steps.map((s) => s.agent_id).join(", ")}
                      </td>
                      <td>
                        <span className={`dot dot-${active ? "on" : "off"}`} />
                        {active ? "actif" : st === "" ? "jamais lance" : st}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="camp-eye"
                          title={
                            latestRun
                              ? "Voir le run de la campagne (frames, verdict, traces)"
                              : "Aucun run -- lance la campagne d'abord"
                          }
                          aria-label={`Voir le run de ${c.id}`}
                          disabled={latestRun === undefined}
                          onClick={() =>
                            setViewing({
                              campaign: c,
                              runId: latestRun?.id ?? null,
                              status: latestRun?.status ?? "",
                            })
                          }
                        >
                          <EyeIcon />
                        </button>
                        <button
                          type="button"
                          onClick={() => void run(c.id)}
                          disabled={active}
                        >
                          Lancer
                        </button>
                        <button
                          type="button"
                          className="camp-danger"
                          onClick={() => void remove(c.id)}
                        >
                          Suppr
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}

      {tab === "recordings" && (
        <section className="panel" role="tabpanel">
          <h2>Enregistrements (replay I4)</h2>
          {replayResult && (
            <p className="camp-replay">
              Replay determinisme :{" "}
              <span
                className={`pill ${replayResult.data.matches_original ? "pill-ok" : "pill-bad"}`}
              >
                {replayResult.data.matches_original ? "IDENTIQUE" : "DIVERGENT"}
              </span>
            </p>
          )}
          {recordings.length === 0 ? (
            <p className="camp-empty">Aucun enregistrement. Lance une campagne.</p>
          ) : (
            <table className="camp-table">
              <thead>
                <tr>
                  <th>Recording</th>
                  <th>Agent</th>
                  <th>Etapes</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {recordings.map((r) => (
                  <tr key={r.recording_id}>
                    <td className="camp-mono">{r.recording_id}</td>
                    <td>{r.agent_id}</td>
                    <td>{r.steps}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => void replay(r.recording_id)}
                        disabled={stream.running}
                      >
                        Replay
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {tab === "create" && (
        <section className="panel" role="tabpanel">
          <h2>Nouvelle campagne</h2>
          <label className="camp-field">
            <span>Id</span>
            <input value={newId} onChange={(e) => setNewId(e.target.value)} />
          </label>
          <label className="camp-field">
            <span>Description</span>
            <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
          </label>
          <fieldset className="camp-agents">
            <legend>
              Agents (etapes, dans l'ordre) -- leurs actions viennent de l'onglet
              Agents
            </legend>
            {agents.length === 0 && (
              <p className="camp-empty">Aucun agent configure.</p>
            )}
            {agents.map((a) => (
              <label key={a.id} className="camp-agent-row">
                <input
                  type="checkbox"
                  checked={picked.includes(a.id)}
                  onChange={() => togglePick(a.id)}
                />
                {a.id} ({a.target_system ?? "?"}) --{" "}
                {(a.capability_scope ?? []).join(", ") || "aucune action"}
              </label>
            ))}
          </fieldset>
          <button type="button" onClick={() => void create()}>
            Creer la campagne
          </button>
        </section>
      )}

      <section className="panel camp-runconsole">
        {stream.runId !== null && (
          <p className="camp-status">
            run {stream.runId} -- {stream.status}
          </p>
        )}
        <LogConsole title="Console du run" lines={stream.frames.map(frameToLogLine)} />
      </section>

      {viewing !== null && (
        <AgentRunModal
          open
          agentId=""
          campaignId={viewing.campaign.id}
          steps={viewing.campaign.steps}
          runId={viewing.runId}
          status={viewing.status}
          runs={runs}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  );
}
