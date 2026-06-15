/**
 * Detailed help content for each console page.
 *
 * The UI copy is in French (operator-facing), while identifiers, keys and
 * comments stay in English (R12). Each topic explains what the page governs,
 * which inspect_ia_agents invariants it enforces, the meaning of every field and
 * action, and the failure-safe behaviour the operator should expect.
 */

import type { ReactNode } from "react";

import Mermaid from "./Mermaid";

/** The full red-team loop: /sim catches -> promote -> corpus -> report. */
const REDTEAM_LOOP_CHART = `flowchart LR
  SIM["/sim attrape l'anomalie<br/>(recette redteam)"] -->|"Promouvoir<br/>(recette redteam-promote)"| CORP
  CORP["corpus/agents (git)<br/>corpus/maf_agents (MAF)<br/>incorrect/&lt;slug&gt;/"] --> REC
  REC["page Recette<br/>(recette run)"] --> REP(["LE RAPPORT"])
  CORP --> VER["page Verdicts"]
  VER --> REP`;

/** The shared Lane B engine: cockpit and /sim both call run_agent + judge. */
const REDTEAM_ENGINE_CHART = `flowchart TD
  A1["agent (Agents/Campagnes)<br/>LLM live + forge reelle"] --> RA
  S1["/sim git red-team<br/>ReplayLlm + LabForge"] --> RA
  RA["lane_b.run_agent<br/>(decide puis act)"] --> JG["judge_subject<br/>(4 dimensions)"]
  JG --> VD{"verdict"}`;

export type HelpTopicKey =
  | "dashboard"
  | "cockpit"
  | "recette"
  | "corpus"
  | "redteam"
  | "campaigns"
  | "recette_campaigns"
  | "verdicts"
  | "flux"
  | "agents"
  | "ai_backends"
  | "servers"
  | "catalog"
  | "approvals"
  | "audit"
  | "live"
  | "proxy";

export interface HelpTopic {
  /** Modal title. */
  title: string;
  /** One-line summary shown under the title. */
  summary: string;
  /** Rich body rendered inside the modal. */
  body: ReactNode;
}

export const HELP_TOPICS: Record<HelpTopicKey, HelpTopic> = {
  recette_campaigns: {
    title: "Aide — Campagnes recette",
    summary:
      "Catalogue read-only des scenarios de gouvernance (campaigns/**) juges par le harness. Distinct des campagnes Lane B.",
    body: (
      <>
        <p>
          Cette page liste les <strong>campagnes de recette</strong> du dossier{" "}
          <code>campaigns/**</code> : des scenarios de gouvernance ou chaque{" "}
          <strong>action</strong> porte un <strong>verdict attendu</strong>
          (<code>allow</code> / <code>deny</code> / <code>escalate</code>), juges
          par le harness (<code>python -m recette</code>). C&apos;est de la{" "}
          <strong>lecture seule</strong> : on ne lance ni ne modifie rien ici.
        </p>
        <h3>Ce n&apos;est PAS la page Campagnes</h3>
        <p>
          A ne pas confondre avec <strong>Campagnes</strong> (CRUD) : celle-ci
          gere des sequences Lane B <code>{"{id, description, steps}"}</code> que
          le dashboard <strong>lance en direct</strong>. Les campagnes recette
          sont un autre objet (<code>{"{name, objective, teaching, agents, actions}"}</code>),
          scorees hors UI. Memes mot, deux concepts -- ce ne sont pas des
          doublons.
        </p>
        <h3>Expliquer</h3>
        <p>
          Le bouton <strong>Expliquer</strong> ouvre un modal (comme pour un
          agent ou un sujet) : l&apos;<strong>objectif</strong> et la{" "}
          <strong>pedagogie</strong>, la liste des <strong>actions</strong> avec
          leur verdict attendu et leur justification, les <strong>agents</strong>
          semes, et le JSON brut. Une famille (bnp, coverage, role-matrix, rag)
          regroupe les campagnes par origine. Un fichier invalide est signale en
          rouge, jamais masque.
        </p>
      </>
    ),
  },
  flux: {
    title: "Aide — Flux",
    summary:
      "Fenetre d'analyse du flux d'audit des agents + lancement d'une boucle APEX. Lecture seule sur le journal (I1).",
    body: (
      <>
        <p>
          Cette page tail le <strong>journal d'audit</strong> des agents
          (<code>/audit</code>, fenetre bornee) et analyse chaque evenement dans
          l'editeur Monaco a droite. Lecture seule de bout en bout : le journal
          est immuable (I1), la page n'ecrit jamais.
        </p>
        <h3>Lancer APEX</h3>
        <p>
          Choisir un agent puis <strong>Lancer APEX</strong> demarre cet agent
          (run Lane B via <code>/runs</code>) : il decide et agit en direct
          contre sa cible, et chaque action gouvernee remonte aussitot dans le
          flux ci-dessous. Le bouton est inactif tant qu'aucun agent n'est
          choisi (rien a lancer). Le run passe par le vrai chemin de gouvernance
          (Gateway {"->"} policy {"->"} proxy), il n'y a pas d'execution hors
          Control Plane (I2).
        </p>
        <h3>Modes d'analyse</h3>
        <ul>
          <li>
            <strong>event</strong> : l'evenement selectionne (clic sur une ligne)
            en JSON formate.
          </li>
          <li>
            <strong>stream</strong> : toute la fenetre visible en JSONL, filtrable
            par <code>action_type</code>, <code>target_system</code>, risque
            minimal.
          </li>
          <li>
            <strong>diff</strong> : comparer deux evenements (A / B) de la fenetre.
          </li>
        </ul>
        <p>
          Le filtre <strong>Agent</strong> (et le lien profond{" "}
          <code>?agent_id=</code>) restreint le tail a un agent ;{" "}
          <code>?seq=</code> pre-selectionne un evenement. L'export{" "}
          <strong>Export window (JSONL)</strong> ne sort que la fenetre visible
          (bornee), pas tout le journal.
        </p>
      </>
    ),
  },
  live: {
    title: "Aide — Flux temps reel",
    summary:
      "Diffusion en direct des evenements gouvernes (SSE). Vue derivee, jamais la source de verite (I1).",
    body: (
      <>
        <p>
          Cette page ouvre un flux <strong>Server-Sent Events</strong> vers{" "}
          <code>/events/stream</code> et affiche chaque evenement gouverne des
          qu'il est ajoute au journal : <code>action_executed</code>,{" "}
          <code>action_denied</code>, <code>action_requested</code>,{" "}
          <code>approval_resolved</code>, <code>platform_error</code>.
        </p>
        <h3>Vue derivee, pas la verite (I1)</h3>
        <p>
          Le transport temps reel ne remplace pas l'event store : il en diffuse
          une <strong>copie</strong>. Un evenement perdu cote temps reel reste
          dans le journal append-only et se retrouve via l'onglet{" "}
          <strong>Audit</strong> (rejouable). Une reconnexion ne rejoue pas
          l'historique ; elle reprend le tail courant.
        </p>
        <h3>Etat du transport</h3>
        <ul>
          <li>
            <strong>Connecte / Deconnecte</strong> : etat du flux SSE du
            navigateur.
          </li>
          <li>
            <strong>Degrade</strong> : le bus aval (NATS) est injoignable ; les
            evenements sont mis en tampon borne et retentes (jamais d'execution
            externe entre-temps, failure-modes). En Phase 1 (transport in-process)
            ce drapeau reste toujours faux.
          </li>
          <li>
            <strong>En attente / Abandonnes</strong> : taille du backlog de
            retry et nombre de copies evincees d'un backlog plein (toujours
            recuperables depuis le journal).
          </li>
        </ul>
        <p>
          Quand le transport est degrade, le backlog est rejoue au retour du
          bus. Ce drainage peut aussi etre force a intervalle regulier par le
          heartbeat de maintenance autonome (module <code>scheduler/</code>, G8,
          opt-in <code>INSPECT_IA_AGENTS_SCHEDULER=inproc</code>) : il ne touche qu'une
          vue derivee, jamais l'event store (I1). Detail :{" "}
          <code>docs/runbooks/autonomous-scheduler.md</code>.
        </p>
      </>
    ),
  },
  dashboard: {
    title: "Aide — Tableau de bord",
    summary:
      "Vue de controle : lance chaque agent (IA reelle) contre le lab et suit son statut en direct.",
    body: (
      <>
        <p>
          Le tableau de bord liste tous les agents runtime du banc et permet de
          les <strong>lancer / arreter</strong> et de voir leur{" "}
          <strong>statut</strong> en direct (rafraichi toutes les 2s).
        </p>
        <p>
          Les cartes KPI en haut resument le banc : agents, agents actifs,
          repartition IA/cible, et le compte de <strong>launches reussis</strong>{" "}
          (runs <code>completed</code>) vs <strong>rates</strong> (runs{" "}
          <code>failed</code>), agrege sur tous les runs -- un agent instable
          reste visible meme si un run vert plus recent masque son echec dans la
          colonne Statut.
        </p>
        <h3>Que fait le bouton Lancer ?</h3>
        <p>
          <strong>Lancer</strong> demarre un run <code>lane_b</code> : l'agent
          tourne sa boucle <em>decide -&gt; agit</em>. Son LLM (IA reelle, via
          l'ai_backend lie -- ex <code>groq-llama</code>, cle resolue en env R8)
          decide une action a la fois, <strong>limitee a son capability_scope</strong>,
          et chaque action part par le proxy (I5) vers le <strong>lab</strong>{" "}
          (plateforme simulee, <code>:8082</code>). <strong>Aucun effet de bord
          reel</strong> : le lab simule okta / github / finance.
        </p>
        <p>
          Un retour immediat confirme le clic (bouton <code>Lancement...</code>{" "}
          puis banniere <code>Run lance pour &lt;agent&gt;</code>). Les frames
          arrivent en direct : <code>start</code>, un <code>step</code> par
          action, <code>result</code>, <code>end</code>. Le statut passe a{" "}
          <code>completed</code> a la fin -- <code>completed</code> signifie que le
          run s'est <em>deroule</em>, pas qu'une gouvernance l'a autorise (le
          chemin lane_b n'evalue pas de policy et n'ecrit pas l'audit : voir plus
          bas).
        </p>
        <h3>Que fait le bouton Lancer precis ?</h3>
        <p>
          <strong>Lancer precis</strong> ouvre une <em>instance</em> : un run
          scripte ou tu choisis exactement les <strong>actions</strong> (cochees
          = le capability_scope de l'agent, plus toute action{" "}
          <code>hors-scope</code> pour tester le depassement), une{" "}
          <strong>ressource</strong> par action, un <strong>profil</strong>{" "}
          attendu (<code>legit</code> / <code>suspect</code> /{" "}
          <code>destructif</code>) et une <strong>repetition</strong>. On
          distingue ainsi l'<strong>agent</strong> (sa definition) de son{" "}
          <strong>instance</strong> (un cas de test concret). Le scenario est
          deterministe (I4) et part par le proxy (I5), comme un run normal.
        </p>
        <p>
          A la fin, un <strong>verdict</strong> en ligne juge le run sur deux
          dimensions :{" "}
          <strong>capability</strong> (une action hors capability_scope qui
          s'execute = <code>capability_overreach</code>) et{" "}
          <strong>policy</strong> (selon le profil : <code>legit</code> attend
          tout autorise ; <code>suspect</code>/<code>destructif</code> attendent
          un blocage). Un refus du proxy fait <em>echouer</em> le run (le forge
          leve sur un resultat non-ok) -- c'est ce blocage que le verdict lit.
          Le verdict s'appuie sur les frames du run, independamment de{" "}
          <code>INSPECT_IA_AGENTS_PROXY_DEBUG</code>.
        </p>
        <h3>Arret anticipe sur boucle (stop-on-repeat)</h3>
        <p>
          Un modele live peut re-demander la meme action (meme outil + meme
          ressource) en boucle jusqu'a la limite d'etapes. Le run{" "}
          <strong>s'arrete des qu'une action deja faite se repete</strong>, donc
          le journal ne garde que les actions <strong>distinctes</strong>. C'est
          deterministe (fonction des decisions, I4) et actif uniquement sur le
          chemin live (jamais en replay).
        </p>
        <h3>IA reelle / cible</h3>
        <ul>
          <li>
            <strong>IA</strong> : <code>IA reelle</code> (un vrai LLM decide, via
            l'ai_backend) ou <code>Mock</code> (scenario scripte, deterministe,
            zero cle). Les backends se gerent dans l'onglet <strong>IA</strong> ;
            le choix par agent (ai_mode + ai_backend) dans l'onglet{" "}
            <strong>Agents</strong>.
          </li>
          <li>
            <strong>En face (cible)</strong> : <code>Simulee (lab)</code> (defaut,
            zero effet de bord) ou <code>Reelle</code> (vrai serveur, tokens).
          </li>
          <li>
            <strong>Agent a scope vide</strong> (ex <code>camp-rogue-bot</code>,{" "}
            <code>camp-marketing-bot</code>) : en IA reelle aucun outil ne lui est
            expose -&gt; <strong>0 action</strong> (inerte). Son cas de
            depassement n'existe qu'en mock (scenario force l'action hors scope).
          </li>
        </ul>
        <h3>Le voyant et l'oeil</h3>
        <ul>
          <li>
            <strong>Voyant</strong> : vert = run actif (pending/running) ; sinon le
            dernier resultat (completed / failed / stopped) ou inactif.
          </li>
          <li>
            <strong>Oeil</strong> : ouvre la modale du run -- onglet{" "}
            <em>Run courant</em> (les frames JSON en direct), onglet{" "}
            <em>Decide {"->"} Action</em> (la decision du LLM en regard de l'effet
            de bord qu'elle a produit : le &laquo; pourquoi &raquo; de chaque
            action), onglet <em>Historique</em> (log detaille par run, horodate,
            grandit a chaque relance) et onglet <em>Verdict recette</em> (jugement
            des 4 dimensions
            identite / capabilities / policy / comportement : l'ecart entre ce que
            l'agent declare et ce qu'il a reellement fait -- read-model
            deterministe I4, jamais ecrit dans l'audit I1) et onglet{" "}
            <em>Traces proxy</em> (les effets de bord HTTP de CE run, filtres par
            run_id ; necessite <code>INSPECT_IA_AGENTS_PROXY_DEBUG=on</code>).{" "}
            <strong>Purger</strong> vide les runs termines de l'agent -- cela ne
            touche QUE le read-model ephemere, <strong>jamais</strong> l'audit
            append-only (I1).
          </li>
        </ul>
        <h3>Gouvernance : un chemin separe</h3>
        <p>
          Le lane_b lance ici est l'<strong>execution de l'agent</strong> (sujet
          d'identification), pas le chemin de gouvernance. Les verdicts{" "}
          <code>allow</code> / <code>deny</code> / <code>escalate</code>,
          l'approbation bloquante (I6) et l'event store immuable (I1) vivent dans
          la section <strong>Gouvernance</strong> (onglets Catalog / Approvals /
          Audit / Proxy), aujourd'hui alimentee a part. Pour le detail action par
          action d'un lancement, ouvrir le <strong>Cockpit</strong>.
        </p>
      </>
    ),
  },
  cockpit: {
    title: "Aide — Cockpit",
    summary:
      "Lancer, observer et arreter les agents de test que l'outil discovery doit reperer.",
    body: (
      <>
        <p>
          <strong>inspect_ia_agents</strong> est la <strong>recette de
          l'outil discovery</strong>, pas l'outil lui-meme. Le cockpit produit
          les <strong>sujets de
          test</strong> : des agents que l'on lance pour verifier que l'outil
          discovery sait les reperer et comprendre a quoi ils se connectent.
        </p>
        <h3>La boucle</h3>
        <ul>
          <li>
            <strong>Configurer</strong> un agent (onglet Agents) : identite,
            systeme cible, but, scope, et l'IA derriere (ai_backend).
          </li>
          <li>
            <strong>Choisir le type</strong> : <code>mock</code> (script
            deterministe, zero cle, zero effet de bord) ou <code>IA reelle</code>{" "}
            (le backend lie pilote un vrai LLM, cle resolue en env, R8).
          </li>
          <li>
            <strong>Lancer</strong> : l'agent execute sa boucle decide -&gt; agit
            contre la cible. Le flux live affiche chaque etape et action.
          </li>
          <li>
            <strong>Arreter</strong> : l'arret est cooperatif, l'agent stoppe a
            la prochaine etape.
          </li>
        </ul>
        <h3>Mock ou IA reelle</h3>
        <p>
          Le mock rejoue un script de decisions (reproductible, ideal pour des
          campagnes de recette stables). L'IA reelle laisse un vrai modele
          decider ses actions : utile pour eprouver le discovery sur des
          comportements non scriptes. Les deux produisent le meme journal
          d'actions, donc les memes signaux a reperer.
        </p>
        <p>
          Une fois les agents lances, l'equipe discovery passe son outil dessus
          (onglet Discovery) et l'on compare au ground-truth : repere ? distingue
          a quoi il se connecte ?
        </p>
        <h3>Logs reseau (proxy)</h3>
        <p>
          Sous le flux live, le panneau <strong>Logs reseau</strong> montre les{" "}
          <strong>appels reels que l'agent envoie a son serveur</strong> pendant
          le run (traces du proxy, I5) : une ligne par appel{" "}
          <code>action cible/ressource -&gt; status</code>, les echecs (cible
          injoignable, deny) inclus. C'est la vue debug ; le journal d'audit
          gouverne ne voit pas ces runs lane_b.
        </p>
        <ul>
          <li>
            <strong>Echange agent &lt;-&gt; serveur</strong> : cliquer une ligne
            (ou la derniere, auto-selectionnee) ouvre le detail dans l'editeur. La{" "}
            <strong>requete</strong> = ce que l'agent demande :{" "}
            <code>action_type</code> + <code>resource</code> (ex{" "}
            <code>suspend_user</code> sur <code>acme/jdoe</code>) + un{" "}
            <code>payload</code> (souvent vide, car les args sont dans
            l'action/ressource). La <strong>reponse</strong> = le corps renvoye
            par le serveur. Le selecteur <em>Afficher</em> filtre : depart agent
            (requete), reponse serveur, ou tous.
          </li>
          <li>
            Les selecteurs <em>Agent</em> et <em>Serveur</em> (defaut{" "}
            <em>Tous</em>) restreignent les lignes affichees aux valeurs presentes
            dans le run.
          </li>
          <li>
            Seuls les agents <strong>lies a un serveur</strong> (champ{" "}
            <code>server</code>, proxy HTTP) tracent ; un agent sans{" "}
            <code>server</code> tourne en LabForge en memoire et ne produit aucun
            appel reseau.
          </li>
          <li>
            Le tracage est active par <code>INSPECT_IA_AGENTS_PROXY_DEBUG</code>{" "}
            (R5, pose par <code>recette.sh platform up</code>). Eteint, le panneau
            l'indique au lieu de rester vide.
          </li>
        </ul>
      </>
    ),
  },
  recette: {
    title: "Aide — Recette",
    summary:
      "Lancer la recette discovery / identification sur le corpus et lire le verdict vs ground-truth.",
    body: (
      <>
        <p>
          C'est ici que la boucle se ferme. Le cockpit produit des agents ;
          cette page passe les <strong>outils a recetter</strong> sur le corpus
          de reference et compare au <strong>ground-truth</strong>.
        </p>
        <h3>Discovery</h3>
        <p>
          Lance l'outil discovery sur le corpus de repos, par surface (github,
          gitlab, temporal, openapi, mcp). Pour chaque surface on lit :
          total, <code>passed</code>, faux positifs, faux negatifs, et le
          verdict global. La recette verifie des proprietes invariantes
          (detection, count/dedup, couverture, cible, determinisme), pas les
          valeurs opaques.
        </p>
        <h3>Identification</h3>
        <p>
          Lance l'outil identification sur le corpus d'agents (corrects ET
          incorrects). Pour chaque agent on compare le verdict predit au verdict
          attendu (correct / incorrect). Le taux de detection et le compte de
          faux positifs / negatifs mesurent si l'outil sait dire oui ET non.
        </p>
        <p>
          Les <code>ReferenceAdapter</code> fournis sont l'oracle de reference
          (offline). Un vrai outil se branche en implementant le meme protocole
          d'adaptateur.
        </p>
      </>
    ),
  },
  corpus: {
    title: "Aide — Corpus",
    summary:
      "Tous les sujets de recette, toutes familles : git, MAF, et equipes multi-agents.",
    body: (
      <>
        <p>
          <strong>Le corpus = le corrige.</strong> Pour chaque agent, la bonne
          reponse attendue (correct ou non, et pourquoi). Fige,{" "}
          <em>lecture seule</em> : on n'y lance rien. C'est l'inverse du{" "}
          <strong>Cockpit</strong> (onglet Agents) ou un agent passe l'examen et
          produit sa copie. Ici on lit la reponse attendue ; la-bas on observe ce
          que l'agent a fait. La recette compare les deux.
        </p>
        <p>
          Le corpus liste chaque <strong>sujet de test</strong> apres la fusion
          git / MAF. Filtrer par <strong>famille</strong> :
        </p>
        <ul>
          <li>
            <code>git_agent</code> : action-logs GitHub / GitLab (identite +
            capability_scope), juges sur 4 dimensions.
          </li>
          <li>
            <code>maf_agent</code> : sujets alignes sur le standard Microsoft
            Agent Framework (un seul agent declaratif).
          </li>
          <li>
            <code>maf_orchestration</code> : equipes multi-agents. Cinq styles
            calques sur les builders MAF reels : <code>handoff</code>,{" "}
            <code>sequential</code>, <code>concurrent</code>,{" "}
            <code>group_chat</code>, <code>magentic</code>.
          </li>
        </ul>
        <h3>Les colonnes</h3>
        <p>
          <strong>Category</strong> (correct / incorrect),{" "}
          <strong>Broken axis</strong> (l'unique dimension cassee d'un negatif :
          identity, capabilities, policy ou behavior) et{" "}
          <strong>Expected</strong> (le verdict attendu du ground-truth). Chaque
          negatif casse <strong>exactement une</strong> dimension, ce qui rend la
          precision par axe mesurable.
        </p>
        <h3>Bout en bout et rejouable (I4)</h3>
        <p>
          Une equipe peut etre jouee par un vrai LLM (Groq), enregistree, puis
          <strong> rejouee a l'identique</strong> : le juge est une fonction pure
          de (team, run). Voir le runbook
          <code> docs/runbooks/orchestration-recette.md</code>.
        </p>
        <h3>Derouler un run (viewer)</h3>
        <p>
          Cliquer le nom d'un sujet <code>maf_orchestration</code> ouvre le
          <strong> viewer pas-a-pas</strong> : la timeline routee (hops / tours /
          appels d'outils), le verdict sur les 4 dimensions et le diagramme
          Mermaid du chemin reel. Lecture seule, deterministe.
        </p>
      </>
    ),
  },
  redteam: {
    title: "Aide — Recette red-team",
    summary:
      "Verifie que l'outil d'identification rend le verdict attendu : anomalie attrapee (vrai positif) ou aucune fausse alarme (vrai negatif). Runs figes, deterministes (I4), zero IA live.",
    body: (
      <>
        <p>
          Cet ecran est la <strong>recette red-team</strong> : il verifie que
          l'outil d'identification rend le <strong>verdict attendu</strong> face
          a des sujets adverses. Deux reussites a distinguer :{" "}
          <strong>anomalie attrapee</strong> (un sujet negatif, l'outil dit
          &laquo; incorrect &raquo; = vrai positif) et{" "}
          <strong>conforme sans fausse alarme</strong> (un sujet correct, l'outil
          ne crie pas au loup = vrai negatif). Tout repose sur des{" "}
          <strong>enregistrements figes</strong>, rejoues a l'identique,{" "}
          <strong>deterministes (I4)</strong> : aucune IA live ici, le verdict ne
          depend que de <code>(sujet, action-log)</code>.
        </p>
        <h3>Les quatre onglets</h3>
        <ul>
          <li>
            <strong>Scorecard</strong> : miroir de <code>recette redteam</code> --
            total, <strong>anomalies attrapees</strong> (vrais positifs),{" "}
            <strong>conformes sans fausse alarme</strong> (vrais negatifs),{" "}
            <strong>ratees</strong> (faux negatifs / faux positifs) et la{" "}
            <strong>repartition OWASP</strong> (la categorie d'attaque LLM
            couverte par chaque cas).
          </li>
          <li>
            <strong>Sujets MAF</strong> : les agents alignes Microsoft Agent
            Framework, declarant des <strong>outils</strong> et des{" "}
            <strong>handoffs</strong>. Le coeur de l'ecran (detail ci-dessous).
          </li>
          <li>
            <strong>Agents Git (Lane B)</strong> : les sujets git pilotes par un
            but (<em>goal-driven</em>), juges sur le meme barometre.
          </li>
          <li>
            <strong>Enregistrements figes</strong> : les scenarios d'attaque
            captures, rejouables a l'identique (la matiere de la recette).
          </li>
        </ul>
        <h3>Detail d'un sujet MAF</h3>
        <p>
          Cliquer un sujet MAF ouvre son detail. C'est l'ecart entre ce que
          l'agent <strong>declare</strong> et ce qu'il <strong>fait</strong> sous
          la pression de l'adversaire. Chaque bloc :
        </p>
        <ul>
          <li>
            <strong>Capacites declarees</strong> : les <strong>outils</strong>{" "}
            (<code>tool_kind</code> / <code>target</code>) et les{" "}
            <strong>handoffs</strong> que l'agent DECLARE pouvoir utiliser, avec
            l'<strong>approbation requise</strong> : <code>jamais</code> (libre)
            ou <code>toujours</code> -- ce dernier est une <strong>porte
            I6</strong>, l'outil ne s'execute qu'apres approbation explicite,
            jamais de maniere optimiste.
          </li>
          <li>
            <strong>Verdict 4 dimensions</strong> :{" "}
            <strong>identite</strong> / <strong>capacites</strong> /{" "}
            <strong>politique</strong> / <strong>comportement</strong> (vert =
            conforme, rouge = casse). Pour un negatif, l'unique{" "}
            <strong>axe casse</strong> est l'anomalie (son{" "}
            <code>violation_type</code>) ; les trois autres restent conformes
            (mono-axe).
          </li>
          <li>
            <strong>Timeline d'attaque (escalade crescendo)</strong> :
            l'adversaire (<em>utilisateur = adversaire</em>) pousse l'agent{" "}
            <strong>tour apres tour</strong>, montant progressivement la pression
            jusqu'a l'action sensible visee. La timeline montre cette escalade en
            ordre.
          </li>
          <li>
            <strong>Journal d'actions (declare vs reel)</strong> : chaque action
            reellement faite par l'agent porte le verdict du <strong>juge</strong>{" "}
            -- <strong>conforme</strong> (dans le perimetre declare),{" "}
            <strong>hors perimetre</strong> (outil/handoff non declare ={" "}
            <code>capability_overreach</code>), ou{" "}
            <strong>en attente (approbation requise, non obtenue)</strong> (un
            outil <code>approbation: toujours</code> invoque sans que
            l'approbation soit obtenue = <code>policy_violation</code>, I6).
            C'est ce marquage qui rend l'anomalie lisible action par action.
          </li>
          <li>
            <strong>Promouvoir vers le corpus</strong> : une anomalie attrapee et{" "}
            <strong>mono-axe</strong> peut etre figee en{" "}
            <strong>sujet negatif</strong> (<code>corpus/.../incorrect/&lt;slug&gt;/</code>),
            reutilisable ensuite par la recette. Si le sujet existe deja, le
            bouton devient <strong>Remplacer</strong>.
          </li>
        </ul>
        <h3>Detail d'un agent Git (Lane B)</h3>
        <p>
          L'onglet <strong>Agents Git (Lane B)</strong> attaque la meme chose mais
          sur un agent <strong>GitHub / GitLab</strong>, pilote par un{" "}
          <strong>but</strong> (<em>goal-driven</em>) et non par une conversation :
          au lieu de tours d'utilisateur, l'adversaire fixe un{" "}
          <strong>objectif</strong> ("merger sur main sans review") et l'agent
          tourne en boucle <code>decide -&gt; act</code> contre le lab git. Memes 4
          dimensions, meme barometre que le MAF. Les blocs du detail :
        </p>
        <ul>
          <li>
            <strong>Capacites declarees</strong> : ici ce sont des{" "}
            <strong>actions git</strong> -- chaque <code>action</code>{" "}
            (<code>read_repo</code>, <code>open_pr</code>, <code>merge_pr</code>,
            ...) avec son mode <strong>lecture</strong> / <strong>ecriture</strong>{" "}
            et ses <strong>ressources</strong> (globs de repos autorises). C'est le
            perimetre que l'agent ne doit pas franchir.
          </li>
          <li>
            <strong>Verdict 4 dimensions</strong> : identique au MAF. Pour un
            negatif, l'unique axe casse porte le <code>violation_type</code> --
            p.ex. <code>capability_overreach</code> (un agent read-only qui ouvre
            une PR), <code>policy_violation</code> (un merge sans l'approbation
            requise, I6), <code>identity_mismatch</code> (un principal different de
            celui declare), <code>behavior_anomaly</code> (spam, action hors role).
          </li>
          <li>
            <strong>Objectif</strong> + <strong>Journal d'actions</strong> : pas de
            timeline crescendo (l'agent n'a pas de tours d'utilisateur) -- on voit
            l'<strong>objectif adverse</strong> donne a l'agent, puis chaque action
            reellement executee, taggee par le juge :{" "}
            <strong>conforme</strong> (dans le perimetre) ou{" "}
            <strong>hors perimetre</strong> (action ou ressource non declaree).
            Une <code>injection d'outil</code> optionnelle (sortie de forge
            empoisonnee, facon AgentDojo) peut etre la source du detournement.
          </li>
          <li>
            <strong>Promouvoir</strong> : identique, mais le sujet fige atterrit
            dans <code>corpus/agents/incorrect/&lt;slug&gt;/</code>{" "}
            (<code>manifest.json</code> + <code>scenario.json</code>) -- le tronc
            git du corpus, pas <code>corpus/maf_agents/</code>.
          </li>
        </ul>
        <h3>Le meme moteur que les Agents et les Campagnes</h3>
        <p>
          Le red-team git n'est PAS un moteur a part : c'est{" "}
          <strong>exactement le run d'un agent par une campagne</strong>, mais
          deterministe. Le cockpit (onglet <strong>Agents</strong> /{" "}
          <strong>Campagnes</strong>) et /sim appellent la{" "}
          <strong>meme fonction</strong> <code>lane_b.run_agent</code> (meme boucle{" "}
          <code>decide -&gt; act</code>, memes arguments derives de l'agent :
          agent_id, principal, target_system, goal, capability_scope), et jugent
          avec le <strong>meme juge</strong> d'identification. La seule difference :
          le cockpit branche un <strong>LLM live</strong> + une{" "}
          <strong>forge reelle</strong> (proxy / lab) ; /sim branche un{" "}
          <strong>LLM rejoue</strong> (decisions figees, I4) + un{" "}
          <strong>lab en memoire</strong>. Un sujet red-team est donc le{" "}
          <strong>jumeau fige</strong> d'un run d'agent -- meme action-log, meme
          verdict, mais reproductible. Promouvoir ne cree pas un agent lancable :
          il fige ce jumeau dans le corpus pour la recette d'identification.
        </p>
        <Mermaid
          title="Le meme moteur Lane B (cockpit live et /sim deterministe convergent)"
          chart={REDTEAM_ENGINE_CHART}
        />
        <h3>Le CLI fait la meme chose (l'UI est le miroir)</h3>
        <ul>
          <li>
            <code>recette redteam</code> : produit la scorecard (les compteurs
            ci-dessus).
          </li>
          <li>
            <code>recette redteam-record</code> : enregistre une attaque live et
            la fige en scenario rejouable.
          </li>
          <li>
            <code>recette redteam-promote</code> : fige une anomalie attrapee en
            sujet negatif du corpus.
          </li>
        </ul>
        <h3>Et apres ? (le lien avec la plateforme)</h3>
        <p>
          Promouvoir <strong>n'ajoute ni agent runtime ni campagne</strong> : il
          ecrit un <strong>sujet de test fige</strong> (la verite de reference)
          dans le corpus d'identification (<code>corpus/agents/</code> pour git,{" "}
          <code>corpus/maf_agents/</code> pour MAF). Ce sujet est ensuite{" "}
          <strong>note</strong> par la recette d'identification :
        </p>
        <ul>
          <li>
            <strong>page Recette</strong> (<code>recette run</code>) : rejoue le
            corpus et donne la <strong>scorecard d'identification</strong> --
            l'outil externe attrape-t-il l'anomalie figee ?
          </li>
          <li>
            <strong>page Verdicts</strong> : les verdicts soumis par l'outil
            externe, juges contre ce meme ground-truth.
          </li>
        </ul>
        <h3>Le lien avec les Agents et les Campagnes (la confusion frequente)</h3>
        <p>
          /sim travaille sur des <strong>sujets figes</strong> (cote
          identification), pas sur des agents vivants. Promouvoir{" "}
          <strong>n'ajoute NI agent runtime</strong> (onglet{" "}
          <strong>Agents</strong>, les agents que tu LANCES){" "}
          <strong>NI campagne</strong> (onglets <strong>Campagnes</strong>, qui
          orchestrent des runs live). Un meme agent porte{" "}
          <strong>trois formes</strong> : l'agent runtime (qu'on lance), le sujet
          d'identification (un action-log fige, ce que juge /sim et la page
          Recette), et le sujet de discovery (un vrai repo). /sim vit dans la
          deuxieme forme uniquement. Le cockpit (Agents/Campagnes) et /sim
          alimentent la <strong>meme</strong> cible d'identification, mais l'un en
          lancant un agent, l'autre en figeant une attaque enregistree.
        </p>
        <p>
          La boucle : <strong>/sim attrape</strong> -&gt;{" "}
          <strong>Promouvoir fige</strong> dans{" "}
          <code>corpus/agents</code> (git) ou <code>corpus/maf_agents</code>{" "}
          (MAF) -&gt; <strong>Recette/Verdicts notent</strong>. C'est la que se lit
          le rapport, pas dans /sim.
        </p>
        <Mermaid
          title="La boucle : /sim attrape, Promouvoir fige, Recette/Verdicts notent"
          chart={REDTEAM_LOOP_CHART}
        />
      </>
    ),
  },
  campaigns: {
    title: "Aide — Campagnes",
    summary:
      "Jeux d'agents persistes, lances a la demande, avec replay deterministe (I4). Ecran en 4 onglets, modeles regroupes par domaine d'activite.",
    body: (
      <>
        <p>
          Une <strong>campagne</strong> est un ensemble ordonne et persiste de
          lancements d'agents que l'equipe discovery rejoue a la demande. Chaque
          execution passe par le vrai chemin (cockpit), diffuse son flux live, et
          enregistre <strong>un enregistrement par etape</strong>.
        </p>
        <h3>Les quatre onglets</h3>
        <p>
          L'ecran etait trop dense en une seule vue : il est decoupe en onglets,
          et la <strong>console du run</strong> reste affichee en bas, visible
          depuis n'importe quel onglet.
        </p>
        <ul>
          <li>
            <strong>Modeles par domaine</strong> : le catalogue de modeles
            regroupe par <strong>domaine d'activite</strong> (voir ci-dessous).
          </li>
          <li>
            <strong>Campagnes</strong> : les campagnes persistees ; les{" "}
            <strong>lancer</strong> ou les <strong>supprimer</strong>, avec leur
            statut (poll de <code>/runs</code>).
          </li>
          <li>
            <strong>Enregistrements</strong> : les recordings et le{" "}
            <strong>replay deterministe</strong> (I4).
          </li>
          <li>
            <strong>Creer</strong> : le constructeur manuel (id, description,
            agents coches dans l'ordre).
          </li>
        </ul>
        <h3>Modeles par domaine d'activite</h3>
        <p>
          Les modeles sont ranges par <strong>domaine metier</strong> (IAM,
          Finance, Code &amp; CI/CD, CRM, Collaboration, Cloud, Donnees, RH,
          Support, Juridique, Produit) plutot que par <code>target_system</code>{" "}
          brut. Dans chaque domaine, chaque ligne est une{" "}
          <strong>situation</strong> reperee par son profil :{" "}
          <code>legit</code> (autorise), <code>suspect</code> (depassement),{" "}
          <code>destructif</code> (irreversible). <strong>Instancier</strong> seme
          l'agent mock et sa campagne, prets a lancer.
        </p>
        <h3>Campagne domaine (spectre complet)</h3>
        <p>
          Le bouton <strong>Creer la campagne domaine</strong> instancie toutes
          les situations manquantes du domaine puis cree{" "}
          <strong>une seule campagne</strong> qui les enchaine dans l'ordre
          escaladant <code>legit -&gt; suspect -&gt; destructif</code>. En un clic,
          on couvre l'ensemble des comportements d'un domaine -- la matiere ideale
          pour eprouver l'outil discovery/identification sur un perimetre metier
          coherent (id <code>domaine-&lt;systeme&gt;-spectre</code>).
        </p>
        <h3>Creer / lancer</h3>
        <ul>
          <li>
            Choisir un id, une description, et les agents (les etapes, dans
            l'ordre). Par defaut chaque etape utilise le mode de l'agent (mock si
            aucun ai_backend lie).
          </li>
          <li>
            <strong>Lancer</strong> execute toutes les etapes a la suite et
            persiste les enregistrements.
          </li>
          <li>
            <strong>Oeil</strong> : ouvre la modale du run de la campagne (frames
            ordonnes start / step / result / end, verdict de recette, traces
            proxy). Inactif tant que la campagne n&apos;a jamais ete lancee (rien
            a voir).
          </li>
        </ul>
        <h3>Replay (I4)</h3>
        <p>
          Un enregistrement rejoue les decisions exactes de l'agent et compare le
          journal d'actions au journal d'origine. <code>IDENTIQUE</code> prouve le
          determinisme (meme entree -&gt; meme sortie) ; <code>DIVERGENT</code>
          signale une source de non-determinisme a corriger. C'est ce qui rend une
          campagne de recette stable et reproductible dans le temps.
        </p>
      </>
    ),
  },
  verdicts: {
    title: "Aide — Verdicts",
    summary:
      "Juger les resultats des outils discovery / identification contre le ground-truth des agents.",
    body: (
      <>
        <p>
          Cette page ferme la boucle de recette cote <strong>outils
          externes</strong>. Un outil (discovery ou identification) soumet ses
          resultats ; la plateforme les compare au <strong>ground-truth</strong>{" "}
          declare sur chaque agent (champ <code>ground_truth</code> de l'onglet
          Agents) et rend un statut par agent.
        </p>
        <h3>Statuts</h3>
        <ul>
          <li>
            <strong>PASS</strong> : toutes les verifications declarees par le
            ground-truth correspondent au resultat soumis.
          </li>
          <li>
            <strong>FAIL</strong> : au moins une verification diverge (ex.
            detecte alors que non detectable = faux positif), ou l'agent soumis
            est inconnu de la plateforme.
          </li>
          <li>
            <strong>SKIP</strong> : l'agent ne declare aucun ground-truth, rien
            n'est jugeable (jamais PASS par vacuite).
          </li>
        </ul>
        <h3>Scorecard</h3>
        <p>
          Le bandeau agrege la derniere soumission : total / passes / ignores,
          taux de detection, exactitude par dimension (identite, capacites,
          policy, comportement — <code>n/a</code> quand aucun agent ne porte la
          dimension), faux positifs et faux negatifs. Les taux sont des
          fractions deterministes (I4), calculees uniquement sur les agents qui
          declarent la verification.
        </p>
        <h3>Soumettre des resultats</h3>
        <ul>
          <li>
            <strong>HTTP</strong> : l'outil POSTe sur <code>/verdicts</code> un
            corps <code>{"{tool, results: [...]}"}</code> (un resultat par
            agent : <code>detected</code>, <code>verdict</code>,{" "}
            <code>identity</code>, <code>dimensions</code>).
          </li>
          <li>
            <strong>Upload</strong> : deposer le meme JSON via la zone d'upload
            de la page ; il est valide cote client puis soumis tel quel.
          </li>
          <li>
            <strong>Depuis un run (console)</strong> : apres avoir lance un
            agent, l'oeil de l'agent (onglet <em>Verdict recette</em>) propose{" "}
            <strong>Soumettre aux Verdicts</strong> ; le tableau de bord le fait
            automatiquement a la fin d'un run. La plateforme juge le journal
            d'actions reel de ce run (<code>judge_run</code>, pur et
            deterministe I4) et POSTe le resultat sur{" "}
            <code>/runs/&#123;id&#125;/submit-verdict</code> sous l'outil{" "}
            <code>run:&lt;id&gt;</code>. C'est la boucle interne lancer {"->"}{" "}
            agir {"->"} juger {"->"} Verdicts, sans outil externe.
          </li>
        </ul>
        <p>
          Chaque ligne se deplie : verifications passees / echouees, attendu vs
          observe, et les <strong>evenements de preuve</strong> (les evenements
          d'audit de l'agent au moment de la soumission), relies au journal
          d'audit immuable (I1).
        </p>
        <h3>Historique des soumissions</h3>
        <p>
          Sous la derniere soumission, le panneau{" "}
          <strong>Historique des soumissions</strong> liste toutes les
          soumissions (outil / run, <code>seq</code>, compteurs PASS / FAIL /
          SKIP), de la plus recente a la plus ancienne. Append-only : une
          nouvelle soumission ne reecrit jamais les precedentes.
        </p>
      </>
    ),
  },
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
        <h3>Corpus vs Cockpit -- a ne pas confondre (image de l'ecole)</h3>
        <p>
          Une recette se lit comme un <strong>examen</strong> :
        </p>
        <ul>
          <li>
            <strong>Corpus = le corrige.</strong> Pour chaque agent, la bonne
            reponse attendue (correct ou non, et pourquoi). Fige,{" "}
            <em>lecture seule</em> : on n'y lance rien. C'est l'etalon contre
            lequel un outil externe est juge (&laquo; voici la bonne reponse, ton
            outil tombe-t-il dessus ? &raquo;).
          </li>
          <li>
            <strong>Cockpit = faire passer l'examen.</strong> On{" "}
            <strong>lance</strong> un agent ; il agit pour de vrai contre le lab
            et <strong>produit sa copie</strong> (l'action-log : ce qu'il a
            FAIT).
          </li>
          <li>
            <strong>La recette = corriger la copie avec le corrige.</strong> On
            compare ce que l'agent a fait (Cockpit) a la reponse attendue
            (Corpus). Match = pass.
          </li>
        </ul>
        <p>
          Point cle : on ne juge <strong>jamais</strong> un agent sur ce qu'il{" "}
          <em>declare</em> (son manifest / code), mais sur ce qu'il{" "}
          <strong>fait</strong> -- l'echange reseau du log. Le declare peut
          mentir, l'acte non.
        </p>
        <h3>Les quatre onglets</h3>
        <ul>
          <li>
            <strong>Configuration</strong> : l'atelier -- la table des agents
            (creer / editer / supprimer) et le formulaire. Le bouton{" "}
            <em>Run</em> de chaque ligne lance un run rapide du scenario stocke.
          </li>
          <li>
            <strong>Corpus</strong> : <em>read-only</em>. Tous les sujets de test
            etalons, toutes familles (agents git, sujets MAF, equipes
            d'orchestration), avec leur categorie, l'<strong>axe casse</strong>{" "}
            des negatifs (violation_type) et le <strong>verdict attendu</strong>.
            C'est la verite jugee, pas un agent qui tourne.
          </li>
          <li>
            <strong>Cockpit -- lancer &amp; debug</strong> : le banc de lancement
            detaille (mock / IA reelle, script editable), le flux live, et le{" "}
            <strong>log reseau</strong> (echange agent &lt;-&gt; serveur :
            requete + reponse).
          </li>
          <li>
            <strong>Run log</strong> : la copie -- le journal live des frames
            (start → step → result → end) du run lance par le bouton{" "}
            <em>Run</em> de la table <strong>Configuration</strong>. Il est{" "}
            <strong>vide tant qu'aucun run n'a ete lance par ce bouton</strong> :
            le <strong>Cockpit</strong> a son propre flux live, separe de cet
            onglet (lancer depuis le Cockpit ne remplit PAS le Run log).
          </li>
        </ul>
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
  ai_backends: {
    title: "Aide — IA (backends)",
    summary:
      "Le catalogue des IA derriere les agents : provider + modele, cle write-only (R8), sonde et prompt libre.",
    body: (
      <>
        <p>
          Cet onglet gere les <strong>backends IA</strong> que les agents
          utilisent en mode <code>IA reelle</code>. Un backend epingle un{" "}
          <strong>provider</strong> et un <strong>modele</strong> ; un agent qui
          porte un <code>ai_backend_id</code> fait decider sa boucle{" "}
          <em>decide -&gt; agit</em> par ce LLM.
        </p>
        <h3>Liste dynamique des providers</h3>
        <p>
          Le menu deroulant <strong>Provider</strong> est servi par l'API
          (<code>GET /config/ai-providers</code>), derive de la factory{" "}
          <code>recette/llm.py</code>. Ajouter un provider cote serveur le fait
          apparaitre ici <strong>sans modifier le frontend</strong>. Le libelle
          a cote du menu indique la variable d'environnement attendue (ex.{" "}
          <code>GROQ_API_KEY</code>) ou &laquo; no key &raquo;.
        </p>
        <h3>La cle API (write-only, R8)</h3>
        <p>
          La cle se saisit <strong>par backend</strong> dans la colonne{" "}
          <strong>Key</strong> : la console l'<strong>envoie</strong> mais ne la
          relit jamais (elle n'affiche que le statut <code>key set</code>). Sans
          cle stockee, l'appel retombe sur la variable d'environnement du
          provider au moment du run. Aucun secret n'est jamais affiche ni
          journalise.
        </p>
        <h3>Tester l'IA</h3>
        <ul>
          <li>
            <strong>Test</strong> : sonde de connectivite. Envoie un{" "}
            <code>ping</code> au provider et affiche la latence plus le mot que
            le modele renvoie (ex. <code>177 ms -- &quot;pong&quot;</code>). Un
            aller-retour reel le prouve ; un point vert = succes, rouge =
            l'erreur (cle absente, reseau, base_url).
          </li>
          <li>
            <strong>Ask the model</strong> : envoie un prompt libre et affiche
            la reponse du modele dans la console <strong>Provider calls</strong>.
          </li>
        </ul>
        <p>
          Chemin de diagnostic, pas de decision : la latence mesuree ici n'entre
          pas dans le replay deterministe (I4).
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
        <h3>Referentiel d'actions sensibles (par design)</h3>
        <p>
          Ce catalogue ne liste que des <strong>actions sensibles</strong> : son
          role est de gouverner le risque, pas de tracer le travail de routine.
          Un role habilite obtient donc <code>escalate</code> (approbation) et un
          role non habilite <code>deny</code> ; le verdict <code>allow</code> est
          rare <strong>par construction</strong> (reserve aux actions reellement
          a faible risque, ex. <code>query_knowledge_base</code>). L'absence de
          chemin <code>allow</code> sur une action n'est pas un trou de policy :
          c'est que l'action n'est pas une operation autorisee de routine.
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
        <h3>Balayage autonome</h3>
        <p>
          Le bouton <strong>Sweep timeouts</strong> declenche le balayage a la
          main, mais il peut aussi tourner <strong>tout seul</strong> : un
          heartbeat de maintenance (module <code>scheduler/</code>, G8) rejoue
          ce meme balayage a intervalle regulier quand il est active
          (<code>INSPECT_IA_AGENTS_SCHEDULER=inproc</code>, defaut <code>off</code>). Il
          n'expire que des timeouts, jamais d'auto-approbation (I6), et reste
          hors du chemin de decision (I4). Un tick en echec est isole et ne tue
          ni la boucle ni l'API (fail-safe). Detail :{" "}
          <code>docs/runbooks/autonomous-scheduler.md</code>.
        </p>
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
  proxy: {
    title: "Aide — Proxy (debug side-effect)",
    summary:
      "Tracer chaque effet de bord passe par le proxy I5 : requete, resultat, side_effect_hash.",
    body: (
      <>
        <p>
          Cette page est la <strong>console de debug du proxy</strong>. Tout effet
          de bord externe passe par un proxy mediatise (invariant I5) ; en mode
          debug, chaque <code>execute()</code> est enregistre comme une{" "}
          <strong>trace</strong> : l'intention (event_id, agent, action, systeme,
          ressource, payload) et le resultat (ok, code, <code>side_effect_hash</code>,
          erreur).
        </p>
        <h3>Activer le mode debug</h3>
        <p>
          Le tracage est <strong>parametrable</strong> (R5) via la variable
          d'environnement <code>INSPECT_IA_AGENTS_PROXY_DEBUG</code> (
          <code>1/true/on</code>). Desactive, le proxy s'execute sans surcout et
          aucune trace n'est enregistree — le bandeau l'indique alors clairement.
        </p>
        <h3>Lire les traces</h3>
        <ul>
          <li>
            <strong>Liste</strong> : une ligne par effet de bord, dans l'ordre{" "}
            <code>seq</code> (monotone, deterministe I4). La pastille{" "}
            <code>ok</code> / <code>fail</code> resume l'issue.
          </li>
          <li>
            <strong>Inspecteur</strong> : selectionner une trace l'affiche en JSON
            (Monaco, lecture seule). Le mode <code>stream</code> serialise tout le
            tampon en JSONL.
          </li>
          <li>
            <strong>Vider</strong> : le tampon est borne et jetable ; le vider ne
            touche jamais le journal d'audit immuable (I1), qui reste la verite.
          </li>
        </ul>
        <h3>Deux altitudes : traces app vs wire (mitmproxy)</h3>
        <p>
          Le selecteur en haut bascule la <strong>source</strong> :
        </p>
        <ul>
          <li>
            <strong>traces app</strong> : la vue applicative ci-dessus
            (<code>ProxyTrace</code>, l'intention au niveau du proxy I5).
          </li>
          <li>
            <strong>wire (mitmproxy)</strong> : la vue <strong>reseau</strong> —
            les octets reellement sur le fil, captures par une surcouche{" "}
            <strong>mitmproxy</strong> optionnelle (conteneur Docker). Affiche la
            requete/reponse HTTP(S) brute par echange. Surcouche OFF par defaut :
            tant qu'elle n'est pas active, le panneau explique comment l'activer
            (<code>./recette.sh wire up</code> puis exporter{" "}
            <code>INSPECT_IA_AGENTS_WIRE_PROXY</code> et relancer l'API). Pour le HTTPS
            des systemes reels, faire confiance au CA mitmproxy
            (<code>./recette.sh wire ca</code> {"->"} <code>INSPECT_IA_AGENTS_WIRE_CA</code>).
          </li>
        </ul>
        <h3>Champ par champ d'une trace</h3>
        <ul>
          <li><code>seq</code> : ordre global monotone (I4), stable meme apres rotation du tampon.</li>
          <li><code>event_id</code> / <code>timestamp</code> : identite et horloge logique capturees de l'evenement (jamais l'horloge murale, I4).</li>
          <li><code>agent_id</code> : qui a emis l'effet de bord.</li>
          <li><code>target_system</code> / <code>action_type</code> / <code>resource</code> : ou, quoi, sur quelle ressource.</li>
          <li><code>request_payload</code> : l'intention envoyee au systeme.</li>
          <li><code>ok</code> / <code>status_code</code> / <code>error</code> : l'issue de l'appel.</li>
          <li><code>side_effect_hash</code> : empreinte de l'effet produit (audit/replay, I1/I5).</li>
          <li>
            <code>run_id</code> : le run d'origine (F3). Le filtre <strong>run_id</strong>
            reduit la liste aux traces d'un seul run — c'est aussi le lien depuis
            l'oeil d'un agent vers SA communication.
          </li>
        </ul>
        <h3>Relier la comm a l'objet de la recette</h3>
        <p>
          Voir la comm ne suffit pas : l'objet de l'app est de juger si un agent
          est <strong>correct</strong>, c'est-a-dire l'ecart entre ce qu'il{" "}
          <strong>declare</strong> (son manifeste) et ce qu'il <strong>fait</strong>{" "}
          (ces traces). Ce jugement vit dans l'onglet <strong>Verdict recette</strong>
          de la modale d'un run (bouton oeil), sur les 4 dimensions :
        </p>
        <ul>
          <li><strong>Identite (I3)</strong> : le principal reel correspond au principal declare.</li>
          <li><strong>Capabilities</strong> : chaque action reste dans le <code>capability_scope</code> declare (sinon <code>undeclared_action</code> / <code>mode_escalation</code> / <code>out_of_scope_resource</code>).</li>
          <li><strong>Policy</strong> : les actions a escalade portent une approbation (I6).</li>
          <li><strong>Comportement</strong> : pas d'anomalie (repetition abusive, hors-role).</li>
        </ul>
        <p>
          Le verdict est un <strong>read-model</strong> calcule a la demande, jamais
          ecrit dans l'event store (I1), et deterministe (I4) : meme action-log
          donne le meme verdict. Il reutilise l'evaluateur de reference de
          l'identification.
        </p>
        <p>
          Lab et reel passent par le meme decorateur de tracage : la console
          montre aussi bien un effet simule qu'un appel SaaS reel allowliste.
        </p>
      </>
    ),
  },
  servers: {
    title: "Aide — Serveurs",
    summary:
      "Registre des serveurs en face des agents : mock local pilotable, URL declaree, SaaS reel.",
    body: (
      <>
        <p>
          Cette page gere le <strong>registre des serveurs</strong> : ce qu'il y
          a &laquo; en face &raquo; d'un agent quand il execute ses actions. Un
          agent qui porte un champ <code>server</code> route ses appels vers
          l'entree correspondante (vrai trafic HTTP) ; sans binding, il garde le
          forge en memoire historique.
        </p>
        <h3>Les trois modes</h3>
        <ul>
          <li>
            <strong>mock_local</strong> : un serveur lab simule, demarre et
            arrete depuis cette page (port dedie). Deterministe, zero effet de
            bord, mais le trafic est <strong>observable</strong> : chaque
            requete ecrit une ligne dans le journal d'acces JSONL — la matiere
            que l'outil discovery peut capter au runtime.
          </li>
          <li>
            <strong>declared_url</strong> : un serveur externe qui parle le
            contrat du lab (<code>POST /&#123;system&#125;/execute</code>). Le
            statut est sonde par requete HTTP.
          </li>
          <li>
            <strong>real_saas</strong> : reference declarative d'un SaaS reel.
            Le run route dessus via un proxy reel allowliste (token en env R8,
            ecritures desactivees par defaut), branche par une factory injectee
            au call-site ; sans cette factory ou hors allowlist, le run echoue
            (fail-safe I5), jamais de repli silencieux vers un autre serveur.
          </li>
        </ul>
        <h3>Cycle de vie et journal</h3>
        <ul>
          <li>
            <strong>Demarrer / Arreter</strong> (mock_local) : pilote un vrai
            processus serveur. Un port occupe renvoie un statut
            <code> down</code> avec l'erreur — ce n'est pas un bug, c'est un
            diagnostic.
          </li>
          <li>
            <strong>Statut</strong> : poll du processus (mock_local), sonde URL
            (declared_url), <code>n/a</code> (real_saas).
          </li>
          <li>
            <strong>Journal d'acces</strong> : tail incremental du JSONL
            (event_id, systeme, action, ressource, statut HTTP). C'est la trace
            cote serveur d'un agent en train d'agir.
          </li>
        </ul>
        <h3>Doubles realistes et test d'action</h3>
        <ul>
          <li>
            Les 14 domaines lab (<code>github gitlab okta finance support_desk
            slack cloud hris legal_dms product_cms data_platform crm
            knowledge_base mcp</code>) ne sont pas des stubs : chaque action
            renvoie des <strong>champs metier</strong> realistes et{" "}
            <strong>valide son entree</strong> — une entree invalide (montant
            negatif, IBAN malforme, payee inconnu) renvoie un{" "}
            <strong>422</strong>, comme le vrai systeme. Tout reste deterministe
            (I4) : meme appel, meme reponse.
          </li>
          <li>
            <strong>Tester</strong> : choisir une action, une ressource et un
            payload JSON, puis lancer un appel reel contre le serveur (chemin
            proxy I5). La reponse brute, le statut HTTP et le{" "}
            <code>side_effect_hash</code> s'affichent — un 422 sur entree
            invalide est un diagnostic attendu, pas un bug.
          </li>
        </ul>
        <p>
          Regle fail-safe : un agent qui reference un serveur supprime ou un
          mode non supporte voit son run <strong>echouer</strong>. Executer des
          effets de bord contre le mauvais systeme violerait I5.
        </p>
      </>
    ),
  },
};
