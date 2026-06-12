/**
 * Detailed help content for each console page.
 *
 * The UI copy is in French (operator-facing), while identifiers, keys and
 * comments stay in English (R12). Each topic explains what the page governs,
 * which AgentRail invariants it enforces, the meaning of every field and
 * action, and the failure-safe behaviour the operator should expect.
 */

import type { ReactNode } from "react";

export type HelpTopicKey = "agents" | "catalog" | "approvals" | "audit";

export interface HelpTopic {
  /** Modal title. */
  title: string;
  /** One-line summary shown under the title. */
  summary: string;
  /** Rich body rendered inside the modal. */
  body: ReactNode;
}

export const HELP_TOPICS: Record<HelpTopicKey, HelpTopic> = {
  agents: {
    title: "Aide — Agents",
    summary:
      "Parametrer l'IA derriere chaque agent et l'identite qui sera resolue par la Gateway.",
    body: (
      <>
        <p>
          Cette page declare <strong>qui</strong> agit. Chaque agent enregistre
          ici est l'identite resolue par la Gateway avant toute decision de
          policy (invariant I3 : aucune action anonyme). Un agent inconnu de
          cette liste est <strong>refuse par defaut</strong> (deny-by-default,
          fail-safe).
        </p>
        <h3>Ce que vous configurez</h3>
        <ul>
          <li>
            <strong>id</strong> : identifiant unique de l'agent, repris tel quel
            dans chaque evenement d'audit (correlation par agent_id).
          </li>
          <li>
            <strong>runtime</strong> : <code>lab</code> (systemes externes
            simules, zero effet de bord reel) ou <code>real</code> (proxies
            reels, credentials detenus par les proxies, jamais ici).
          </li>
          <li>
            <strong>role</strong> : determine le verdict applique a chaque
            action. Un role habilite obtient <code>escalate</code> (approbation
            requise) la ou un role non habilite obtient <code>deny</code>.
          </li>
          <li>
            <strong>capability_scope</strong> : liste des systemes que l'agent
            peut viser (ex. <code>okta, github</code>). Sortir du scope est une
            sur-capacite, detectee comme violation.
          </li>
          <li>
            <strong>system_prompt</strong> et <strong>model</strong> :
            parametrage IA de l'agent (comportement, modele LLM).
          </li>
          <li>
            <strong>ai_backend_id</strong> : backend IA associe. Aucun secret
            (cle API, token) n'est saisi ni affiche ici (R8) : les credentials
            appartiennent aux proxies.
          </li>
        </ul>
        <h3>Actions</h3>
        <p>
          Creer, modifier, supprimer un agent. Ces operations touchent le
          registre de configuration, pas le journal d'audit immuable : modifier
          un agent ne reecrit aucun evenement deja committe.
        </p>
      </>
    ),
  },
  catalog: {
    title: "Aide — Catalogue et policy",
    summary:
      "Parcourir les 118 actions sensibles et editer la policy versionnee qui les autorise.",
    body: (
      <>
        <p>
          Cette page declare <strong>ce qui est permis</strong>. Le catalogue
          liste les 118 actions sensibles sur les 11 systemes (Okta, GitHub,
          CRM, Finance, Donnees, Slack, Support, Cloud, RH, Juridique, Produit).
          La policy associe a chaque triplet{" "}
          <code>(systeme, action, role)</code> un verdict.
        </p>
        <h3>Les trois verdicts</h3>
        <ul>
          <li>
            <strong>allow</strong> : execute immediatement via le proxy.
          </li>
          <li>
            <strong>deny</strong> : refuse, jamais execute, audite.
          </li>
          <li>
            <strong>escalate</strong> : bloque l'execution et cree une demande
            d'approbation (I6). Rien ne s'execute tant qu'un humain n'a pas
            approuve.
          </li>
        </ul>
        <p>
          Le moteur est <strong>deny-by-default</strong> : tout triplet absent
          de la policy est refuse. Certaines actions critiques (ex.{" "}
          <code>delete_logs</code>, <code>disable_sso</code>,{" "}
          <code>delete_kms_key</code>) sont <code>deny</code> absolu pour tous
          les roles.
        </p>
        <h3>Editer la policy</h3>
        <p>
          Vous editez un <strong>brouillon</strong> puis publiez une{" "}
          <strong>nouvelle version</strong>. Une version publiee est immuable
          (I1) : on ne modifie jamais une version existante, on en active une
          nouvelle. La version appliquee est enregistree dans chaque decision,
          ce qui rend le replay deterministe (I4).
        </p>
      </>
    ),
  },
  approvals: {
    title: "Aide — Inbox d'approbation",
    summary:
      "Resoudre les actions en attente : approuver, refuser, expirer les timeouts (I6).",
    body: (
      <>
        <p>
          Cette page est le <strong>point de blocage humain</strong>. Toute
          action dont le verdict est <code>escalate</code> arrive ici en etat{" "}
          <code>pending</code> et n'est <strong>pas executee</strong> tant
          qu'elle n'est pas resolue (invariant I6, jamais d'execution
          optimiste).
        </p>
        <h3>Etats d'une approbation</h3>
        <ul>
          <li>
            <strong>pending</strong> : en attente, execution bloquee.
          </li>
          <li>
            <strong>approved</strong> : l'action s'execute alors via le proxy et
            produit un <code>side_effect_hash</code>.
          </li>
          <li>
            <strong>denied</strong> : l'action est definitivement refusee,
            jamais executee.
          </li>
          <li>
            <strong>timeout</strong> : expiree par le balayage, jamais
            auto-approuvee.
          </li>
        </ul>
        <h3>Actions</h3>
        <ul>
          <li>
            <strong>Approuver / Refuser</strong> : saisir l'approbateur et la
            raison ; la resolution est elle-meme un nouvel evenement (I1, pas de
            mutation de l'evenement initial).
          </li>
          <li>
            <strong>Sweep timeouts</strong> : expire les demandes trop
            anciennes. L'instant courant est passe en entree (capture I4), il
            n'est jamais lu dans le chemin de decision.
          </li>
        </ul>
      </>
    ),
  },
  audit: {
    title: "Aide — Journal d'audit",
    summary:
      "Verite forensique : journal immuable, chaine de hash, replay deterministe.",
    body: (
      <>
        <p>
          Cette page est la <strong>source de verite</strong>. Chaque transition
          (demande, deni, approbation, execution, erreur) est un evenement
          ajoute en append-only (I1) : aucun UPDATE ni DELETE n'est possible, des
          triggers SQLite l'interdisent au niveau base.
        </p>
        <h3>Chaine de hash</h3>
        <p>
          Chaque evenement chaine le hash du precedent (<code>prev_hash</code>).
          Le bandeau d'integrite indique si la chaine est intacte. Une rupture
          signalerait une alteration du journal et declencherait le pipeline de
          validation par replay.
        </p>
        <h3>Lire le journal</h3>
        <ul>
          <li>
            <strong>Filtres</strong> : par agent, systeme cible, type
            d'evenement, sequence de depart.
          </li>
          <li>
            <strong>Payload deplie</strong> : ouvrir un evenement montre son
            contenu complet, dont <code>policy_decision</code> + version de
            policy appliquee et <code>side_effect_hash</code> pour les actions
            executees.
          </li>
        </ul>
        <p>
          Les projections (inbox, listes) sont reconstructibles a partir de ce
          journal : elles sont jetables, le journal ne l'est pas.
        </p>
      </>
    ),
  },
};
