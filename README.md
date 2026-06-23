# recette_agentrail

> Application : **inspect_ia_agents** -- console + plateforme de recette +
> couche de gouvernance runtime pour agents IA.

inspect_ia_agents rend le comportement d'un agent IA **lisible**, **gouvernable** et
**rejouable**. Le repo fournit un CORPUS ground-truth et le harnais qui valide deux
outils externes -- **discovery** (cartographier les agents depuis leurs sources) et
**identification** (juger si un agent est correct sur 4 dimensions) -- sur une
plateforme de gouvernance simulee (policy allow/deny/escalate, approbation humaine
bloquante, audit immuable, replay deterministe).

> C'est un **lab** : il **simule** les decisions gouvernees et produit une
> verite-terrain, il ne **bloque pas** de trafic reel. Son role est de preparer
> la plateforme sur laquelle les outils externes s'exercent et sont scores.
> L'enforcement reel (isolation reseau, blocage du chemin direct) est le travail
> de la plateforme cible, pas de la simulation.

## Principe directeur : pas de recette sans lisibilite

On ne recette que ce qu'on peut observer. La lisibilite se construit a trois niveaux :
ce que l'agent **declare** (manifest : identite, `capability_scope`, `target_system`),
ce qu'il **decide** (action-log, le "pourquoi" par etape), et ce qu'il **fait** vraiment
(l'echange reseau agent <-> serveur : requete + reponse, capture par le proxy).

## En chiffres

| Element | Nombre |
|---------|--------|
| Actions gouvernees (catalogue) | **148** sur **16** systemes |
| Referentiel Annex C (actions sensibles) | **124** |
| Campagnes de recette | **55** (bnp 10, coverage 16, role-matrix 15, multidomain 7, rag 4, top-level 3) |
| Agents runtime (cockpit) | **33** |
| Sujets d'identification git (corpus) | **11** correct + incorrect |
| Sujets MAF (corpus) | **5** |
| Scenarios red-team (corpus/sim) | **15** |
| Repos de discovery (corpus) | **5** |
| Providers LLM | **31** (mock `StubLlm`/`ReplayLlm` + reels) |
| Serveurs lab par-domaine | **13** (`:9101`-`:9113`, mock_local + honeypot) + lab `:8082` |

Chaque action porte une **criticite Annex C** (C1 refus par defaut, C2 escalade
systematique, C3 autorisation conditionnelle, C4 autorisation avec journalisation)
en plus de son `risk_level` et de son verdict (allow/escalate/deny). Source de verite :
`recette/platform/catalog/model.py`.

## Les 5 fonctions de l'application

### 1. Gestion d'agent IA (decide -> act)

CRUD d'agents + lancement de la boucle **Lane B** (`recette/lane_b.py`) : l'LLM decide
un appel d'outil parmi le `capability_scope`, l'outil s'execute via la forge, le resultat
revient en contexte, on itere jusqu'a `final` ou `max_steps`. Outils exposes = exactement
le scope declare (`recette/tools.py`). **31 providers LLM** branchables
(`recette/llm/_registry.py` : anthropic, openai, gemini, groq, mistral, deepseek, xai,
bedrock, ... + `openai_compat` generique), plus `StubLlm`/`ReplayLlm` pour le mode mock
deterministe. Cle resolue depuis le secret-store puis l'env, jamais journalisee (R8).
Config : `config/inspect_ia_agents.config.json`. UI : `console/src/pages/agents/`,
`console/src/pages/ai-backends/`.

### 2. Serveur / lab (les systemes que l'agent appelle)

Un serveur HTTP mock (`recette/lab/mock_server.py`, `:8082`) route `POST
/{target_system}/execute` vers **16 doubles de systemes** (`recette/lab/domains/` :
okta, github, gitlab, finance, crm, slack, support_desk, cloud, hris, legal_dms,
product_cms, knowledge_base, data_platform, comms, compliance, mcp). Doubles **purs et
deterministes** (ids = sha256 des entrees, pas d'horloge, pas de random -- I4), reponses
en enveloppe `{success, data|error}`. **13 serveurs par-domaine** (`:9101`-`:9113`,
modes `mock_local` et `honeypot`) permettent de viser une vraie adresse reseau.

### 3. Discovery (cartographier depuis la source)

La discovery ne voit JAMAIS le runtime : elle scanne un **vrai repo publiable**
(`corpus/repos/`, code + CI/CD + manifest `.inspect_ia_agents`). Le harnais
(`recette/discovery_harness.py`) score un scanner externe (`:8081`) sur des **proprietes
invariantes uniquement** -- detection, count/dedup, couverture `action_pattern`, target,
ordre relatif de risque, presence de policy, determinisme -- jamais les valeurs opaques
(`canonical_agent_id`, score exact). Adaptateurs `reference` (oracle offline) ou `http`
(`recette/adapters.py`, `recette/http_adapter.py`). Publication d'un repo de test :
`python -m recette publish <slug> --owner <org>` (dry-run par defaut).

### 4. Proxy (l'echange reseau, mediatise -- I5)

Tout effet de bord passe par un `ExternalSystemProxy`
(`recette/platform/proxy/`) qui produit un `side_effect_hash` deterministe et n'a JAMAIS
de chemin de contournement (echec -> erreur auditable, pas de fallback silencieux). Le
`TracingProxy` enregistre chaque execution comme **`ProxyTrace`** (request_payload + le
`response` du serveur, status, hash, `seq` monotone) dans un ring buffer borne, surface
dans le log reseau du cockpit. C'est la couche qui rend "ce que l'agent FAIT vraiment"
lisible.

### 5. Red-team (influencer la communication, puis prouver qu'on la rattrape)

Scenarios adversariaux deterministes (`corpus/sim/*.scenario.json` MAF,
`*.git-scenario.json` git) modelisant comment un attaquant influence la communication
agent <-> serveur : **tool injection / context poisoning** (la sortie d'outil est
empoisonnee et pilote la decision suivante), **handoff overreach** (transfert vers un
agent non declare), **identity mismatch**, **approval bypass**, **crescendo coercion**
(4 phases d'escalade). Gate pure rejouable sans cle LLM (`python -m recette redteam`),
recorder (live -> scenario fige avec self-check I4 round-trip), promote (anomalie
attrapee -> sujet de corpus). Scorecard `/sim` ventile par standard **OWASP Agentic 2026
(ASI01-10)** + **MITRE ATLAS**.

## Le fil narratif (de l'observation au controle)

1. **Comprendre la com agent <-> serveur** : le proxy capture requete + reponse
   (`ProxyTrace`), rendant chaque echange lisible (niveau "ce qu'il FAIT").
2. **Montrer qu'on peut l'influencer** : la red-team injecte/empoisonne/coerce et
   demontre qu'un agent non gouverne derive (overreach, bypass, identite divergente).
3. **D'ou la necessite d'un controle deterministe** : meme stream + meme version de
   policy => meme verdict (I4). La decision est une fonction pure, rejouable, auditable.
4. **Passeport crypto apres discovery** : un agent n'est gouverne que s'il est d'abord
   **decouvert** et lie cryptographiquement a une identite (I3, `principal`/`auth_method`) ;
   toute action anonyme ou a l'identite divergente est rejetee.
5. **Regles de controle d'activite** : un catalogue d'actions + des policies versionnees
   (allow/deny/escalate, criticite Annex C, deny-by-default) bornent ce que chaque role
   peut faire ; l'escalade BLOQUE jusqu'a approbation (I6).

Argumentaire complet pour presentation interne :
[docs/argumentaire-inspect-ia-agents.md](docs/argumentaire-inspect-ia-agents.md).

## Captures d'ecran

| Configuration des agents | Cockpit -- lancement | Run log (action-log) |
|---|---|---|
| ![Agents](docs/screenshots/01-agents-config.png) | ![Cockpit](docs/screenshots/02-cockpit-launch.png) | ![Run log](docs/screenshots/03-run-log.png) |

## Installation et demarrage

Prerequis : **Python >= 3.11**, **Node.js + npm >= 20**, `bash`/`curl`/`ss`.
Guide complet : [docs/runbooks/installation.md](docs/runbooks/installation.md).

```
python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e '.[api]'
```

Tout se pilote par `./recette.sh` (menu interactif ou CLI). Une seule commande lance
**le serveur applicatif** (API gouvernee `:8090`) **et les serveurs appeles par les
agents** (lab mock `:8082` + serveurs par-domaine `:9101`-`:9113`) ; puis la console :

```
./recette.sh platform up
./recette.sh console start
```

Ouvrir le **cockpit** sur **http://localhost:5173**. Onglet **Cockpit** : choisir un
agent, mock ou IA reelle, le lancer, suivre le flux live. Onglet **Recette** : scorer
discovery / identification vs ground-truth. Onglet **Campagnes** : jeux d'agents
persistes avec replay deterministe (I4). Arret : `./recette.sh platform down` ; serveur
bloque : `./recette.sh platform purge`.

> Note : l'API tourne sur :8090 (ou 1er port libre 8090-8099, voir `.run/api.port`) --
> port JSON, pas une page web (`GET /` renvoie `404` normalement). L'UX graphique est le
> cockpit sur :5173.

**Documentation de fond** (raison d'etre, architecture, diagrammes, chemin d'execution
gouverne) : [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Composants

| Composant | Description | Doc |
|-----------|-------------|-----|
| **Cockpit (console UX)** | React/Vite : configurer/lancer/arreter des agents (mock ou IA reelle), scorer discovery + identification, campagnes + replay (I4), CRUD ai-backends. | [console/README.md](console/README.md), [recette-sh.md](docs/runbooks/recette-sh.md) |
| **Runs & campagnes** | Lane B (mock/IA), runners discovery/identification, campagnes persistees, enregistrements rejouables. API `/runs`, `/campaigns`, `/recordings` + WebSocket. | [platform.md](docs/runbooks/platform.md) |
| **Plateforme gouvernee (mock)** | Gateway (I2), policy engine versionne (deny-by-default), approbations (I6), event store SQLite append-only hash-chaine (I1), proxy lab (I5). 148 actions / 16 systemes, criticite Annex C. | [platform.md](docs/runbooks/platform.md) |
| **API** | Expose les capacites CLI (identification / discovery / Lane B), config et catalogue en HTTP + WebSocket. Defaut lab forge (zero effet de bord), secrets en env (R8). | [api.md](docs/runbooks/api.md) |
| **Discovery recette** | Corpus de 5 repos de test + scorecard d'invariants pour l'outil de discovery. | [github-discovery-recette.md](docs/runbooks/github-discovery-recette.md) |
| **Red-team** | Scenarios adversariaux deterministes, gate rejouable, recorder/promote, scorecard OWASP ASI 2026 + MITRE ATLAS. | [redteam-recette.md](docs/runbooks/redteam-recette.md) |
| **Lab (doubles realistes)** | 16 domaines simules (`recette/lab/domains/`) : champs metier par action, validation -> 422, deterministes (I4). | [lab-realistic-doubles.md](docs/runbooks/lab-realistic-doubles.md) |

## Tests et qualite

```
./recette.sh test     # unittest stdlib (offline)
./recette.sh gates    # ruff + mypy + bandit
python3 -m recette redteam   # gate red-team deterministe (sans cle LLM)
```

## Licence

Open source / source-available sous **PolyForm Noncommercial License 1.0.0**.
Usage, etude, modification et recette libres et gratuits a des fins **non
commerciales** -- principalement la **recherche** et l'**usage personnel**.
Tout usage commercial requiert une licence separee du mainteneur
(mo0ogly@proton.me). Texte complet : [LICENSE](LICENSE).
