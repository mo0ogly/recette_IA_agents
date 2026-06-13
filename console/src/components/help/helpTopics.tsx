/**
 * Detailed help content for each console page.
 *
 * The UI copy is in French (operator-facing), while identifiers, keys and
 * comments stay in English (R12). Each topic explains what the page governs,
 * which AgentRail invariants it enforces, the meaning of every field and
 * action, and the failure-safe behaviour the operator should expect.
 */

import type { ReactNode } from "react";

export type HelpTopicKey =
  | "dashboard"
  | "cockpit"
  | "recette"
  | "campaigns"
  | "verdicts"
  | "agents"
  | "servers"
  | "catalog"
  | "approvals"
  | "audit"
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
  dashboard: {
    title: "Aide — Tableau de bord",
    summary:
      "Vue de controle : statut de chaque agent et les deux axes mock/reel en un coup d'oeil.",
    body: (
      <>
        <p>
          Le tableau de bord liste tous les agents de recette et permet de les
          <strong> lancer / arreter</strong> et de voir leur <strong>statut</strong>{" "}
          en direct (rafraichi toutes les 2s).
        </p>
        <h3>Les deux axes mock / reel</h3>
        <ul>
          <li>
            <strong>IA</strong> : <code>IA reelle</code> (un vrai LLM decide les
            actions, via l'ai_backend lie, cle en env R8) ou <code>Mock</code>
            (scenario scripte, deterministe, zero cle).
          </li>
          <li>
            <strong>En face (cible)</strong> : <code>Reelle</code> (vrai serveur)
            ou <code>Simulee (lab)</code> (plateforme simulee, zero effet de bord).
          </li>
        </ul>
        <p>
          Les deux se reglent par agent dans l'onglet Agents (champ ai_mode pour
          l'IA, runtime pour la cible). Le pastille verte = un run actif
          (pending/running) ; sinon le dernier resultat (completed/failed/stopped)
          ou inactif.
        </p>
        <p>
          Pour le detail des actions d'un lancement (flux pas a pas), ouvrir
          l'onglet Cockpit.
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
          Cette plateforme est la <strong>recette de l'outil discovery</strong>,
          pas l'outil lui-meme. Le cockpit produit les <strong>sujets de
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
  campaigns: {
    title: "Aide — Campagnes",
    summary:
      "Jeux d'agents persistes, lances a la demande, avec replay deterministe (I4).",
    body: (
      <>
        <p>
          Une <strong>campagne</strong> est un ensemble ordonne et persiste de
          lancements d'agents que l'equipe discovery rejoue a la demande. Chaque
          execution passe par le vrai chemin (cockpit), diffuse son flux live, et
          enregistre <strong>un enregistrement par etape</strong>.
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
        </ul>
        <p>
          Chaque ligne se deplie : verifications passees / echouees, attendu vs
          observe, et les <strong>evenements de preuve</strong> (les evenements
          d'audit de l'agent au moment de la soumission), relies au journal
          d'audit immuable (I1).
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
          d'environnement <code>AGENTRAIL_PROXY_DEBUG</code> (
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
        <p>
          Regle fail-safe : un agent qui reference un serveur supprime ou un
          mode non supporte voit son run <strong>echouer</strong>. Executer des
          effets de bord contre le mauvais systeme violerait I5.
        </p>
      </>
    ),
  },
};
