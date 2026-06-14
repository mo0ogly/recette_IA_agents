# Guide operateur -- `recette.sh` et l'application inspect_ia_agents

`recette.sh` est le point d'entree unique pour piloter toute la recette
inspect_ia_agents : le lab Docker historique (discovery/identification), l'API Track U,
et la **plateforme d'execution gouvernee** (gateway + console UX + campagnes)
ajoutee en vague 1.

Deux modes d'usage :

```
./recette.sh            # menu interactif
./recette.sh <cmd> ...  # CLI non interactif (delegue aux sous-programmes cicd/)
```

Le script ne fait qu'orchestrer ; chaque domaine vit dans `cicd/<domaine>.sh`
(`docker.sh`, `api.sh`, `platform.sh`, `checks.sh`, `git.sh`, `status.sh`),
helpers communs dans `cicd/lib/common.sh`.

---

## 1. Qu'est-ce que l'application ?

C'est une **plateforme de recette des outils discovery et identification**
d'inspect_ia_agents -- PAS ces outils eux-memes. Elle produit les sujets de test
(des agents qu'on configure, lance, arrete) et mesure si l'outil discovery les
repere et si l'identification rend le bon verdict, par comparaison au
ground-truth. Le cockpit (`http://localhost:5173`) pilote tout : configurer des
agents (mock ou IA reelle), les lancer / arreter, faire des campagnes
persistees avec replay deterministe (I4), scorer discovery + identification.

Les briques de **gouvernance** ci-dessous (gateway, policy, approbations,
audit) sont la plateforme cible, presente ici en **mock** (onglets secondaires) ;
elles servent de contexte de reference, pas de chemin de recette courant.

### Gouvernance runtime (mock, reference)

Un agent ne touche jamais un systeme externe sans :

1. une **identite** resolue (I3),
2. une **decision de policy** `allow | deny | escalate` (I2, deny-by-default),
3. en cas de `escalate`, une **approbation humaine bloquante** -- rien ne
   s'execute tant que ce n'est pas approuve (I6),
4. un **effet de bord mediatise** par un proxy qui produit un `side_effect_hash`
   (I5),
5. un **evenement d'audit immuable** chaine par hash (I1).

### Les trois plans

```
        agent / console / campagne / curl
                       |
                       v
   CONTROL  Gateway (recette/platform/gateway.py)
            resolve identite -> normalise en PlatformActionEvent
            -> policy decide (versionnee, deny-by-default)
                 allow    -> execute via proxy
                 deny     -> audite, jamais execute
                 escalate -> pending, BLOQUE (I6)
                       |
                       v
   DATA     LabHttpProxy (I5) -> lab mock :8082 /{systeme}/execute
            -> side_effect_hash enregistre
                       |
                       v
   AUDIT    Event store SQLite append-only, hash-chaine (I1)
            GET /audit/events, GET /audit/verify
```

### Le catalogue : 118 actions sensibles / 11 systemes

Source de verite : `docs/tracking/PLAN_high-risk-action-catalog_2026-06-12.md`.
Code : `recette/platform/catalog/domains/<systeme>.py` (1 module par systeme).

| Systeme | `target_system` | Exemples d'actions |
|---------|-----------------|--------------------|
| Identite / Acces | `okta` | suspend_user, delete_user, disable_sso |
| GitHub / DevOps | `github` | delete_repository, disable_branch_protection |
| CRM / Sales | `crm` | export_customer_base, bulk_modify_deals |
| Finance | `finance` | launch_wire_transfer, trigger_refund |
| Donnees | `data_platform` | delete_logs, extract_data_to_external_llm |
| Slack | `slack` | send_message_as_executive, export_slack_history |
| Support | `support_desk` | export_customer_conversations, delete_ticket |
| Cloud | `cloud` | delete_database, delete_kms_key |
| RH | `hris` | modify_salary, export_employee_data |
| Juridique | `legal_dms` | delete_evidence_item, accept_contract_terms |
| Produit | `product_cms` | publish_production, modify_pricing |

Chaque action porte le verdict attendu (la plupart `escalate` pour un role
habilite, `deny` sinon ; quelques actions sont `deny` absolu pour tous, ex.
`delete_logs`, `delete_audit_evidence`, `disable_sso`, `delete_backups`,
`delete_kms_key`, `send_message_as_executive`, `delete_evidence_item`) et un
niveau de risque (low/medium/high/critical).

### Le cockpit UX (React/Vite, dossier `console/`)

Le cockpit produit les **sujets de test** que les outils discovery /
identification doivent reperer et juger. Ce n'est PAS l'outil discovery.
Six onglets, branches directement sur l'API. Detail : [console/README.md](../../console/README.md).

| Onglet | Role |
|--------|------|
| **Cockpit** | choisir un agent, mode mock (script deterministe) ou IA reelle (ai_backend, cle env), le lancer, suivre le flux live, l'arreter |
| **Recette** | lancer discovery + identification sur le corpus -> scorecard detecte/distingue vs ground-truth (par surface / par agent) |
| **Campagnes** | jeux d'agents persistes lances a la demande ; flux live ; enregistrements rejouables avec verdict IDENTIQUE/DIVERGENT (replay deterministe, I4) |
| **Agents** | definir chaque agent (principal, target_system, goal, capability_scope = actions canoniques, ai_backend) + CRUD des ai-backends (provider+model, zero secret R8) |
| **Catalog** (gouvernance mock) | les 118 actions + editeur de policy |
| **Approvals** (gouvernance mock) | inbox des approbations (I6) |
| **Audit** (gouvernance mock) | journal immuable + chaine de hash |

Chaque onglet porte une modale `? Aide` detaillee. Les onglets Catalog /
Approvals / Audit sont la plateforme de gouvernance (mock), gardes en
secondaire, pas le chemin de recette discovery.

`capability_scope` = liste des **actions canoniques** que l'agent peut appeler
(`read_repo, list_repos, read_ci, open_issue, comment_issue, open_pr, merge_pr,
push, manage_webhook, manage_release, trigger_ci`), pas un nom de systeme.

### Les campagnes (`recette/campaign.py`, dossier `campaigns/`)

Une **campagne** est un fichier JSON declaratif : les agents a creer + une
liste ordonnee d'actions a soumettre, avec un verdict attendu optionnel par
action. Le runner passe par le **vrai chemin gouverne** (rien n'est bypasse),
verifie la chaine d'audit, ecrit un rapport JSON, et sort en code non-zero si
un verdict ne matche pas -- donc utilisable comme recette boite noire.

Campagnes livrees :

| Campagne | Contenu | Resultat attendu |
|----------|---------|------------------|
| `identity-offboarding` | offboarding par un identity admin | 3 escalate (pending) + 1 deny (`disable_sso`) |
| `finance-payment-run` | batch de paiements admin + bot non habilite | 3 escalate + 2 deny |
| `redteam-probe` | 9 actions interdites sur 7 systemes par un bot non habilite | 9 deny, chaine intacte |

---

## 2. Le menu interactif

`./recette.sh` (sans argument) affiche :

```
  Docker lab
   1) Statut global              5) Rebuild image
   2) Demarrer le lab (up)       6) Logs lab
   3) Arreter le lab (down)
   4) Redemarrer le lab
  API Track U
   7) API start    8) API stop    9) API statut
  Checks
  10) Tests (local)   11) Gates (local)   12) Report (local)   13) Tests (docker)
  Git
  14) Git statut   15) Git pull   16) Git push   17) Git sync
  Plateforme gouvernee
  18) Plateforme up (lab mock + API)
  19) Plateforme down
  20) Plateforme statut
  21) Console UX start (http://localhost:5173)
  22) Console UX stop
  Campagnes
  23) Lister les campagnes
  24) Lancer une campagne
  Nettoyage
  25) Purger les serveurs web locaux (API, lab, console)
   0) Quitter
```

### Detail des sections

**Docker lab (1-6)** -- lab historique discovery/identification (`cicd/docker.sh`).
Construit l'image, demarre `discovery-mock`, lance la recette discovery en HTTP.
Sans rapport avec la plateforme gouvernee.

**API Track U (7-9)** -- demarre/arrete l'API *nue* (`cicd/api.sh`,
`python -m recette.api`) sans le cablage plateforme. Pour la plateforme
complete, preferer l'entree 18.

**Checks (10-13)** -- tests unittest, gates (ruff/mypy/bandit), rapport,
variante docker (`cicd/checks.sh`).

**Git (14-17)** -- statut, pull, push, sync (`cicd/git.sh`).

**Plateforme gouvernee (18-22)** -- le coeur vague 1 (`cicd/platform.sh`) :

- **18 Plateforme up** : demarre le lab mock (:8082, 11 systemes simules) PUIS
  l'API avec tout le cablage (URL lab, event store SQLite, dossier policies).
  Choisit automatiquement un port libre (8090-8099) si 8090 est occupe par un
  autre service local, et le persiste dans `.run/api.port`.
- **19 Plateforme down** : arrete API + lab (+ console si demarree).
- **20 Plateforme statut** : pid/port de chaque service + `GET /audit/verify`
  (etat de la chaine de hash).
- **21 Console UX start** : `npm install` au premier lancement, puis vite dev
  sur :5173, `VITE_INSPECT_IA_AGENTS_API_URL` cable sur le port API resolu.
- **22 Console UX stop**.

**Campagnes (23-24)** :

- **23 Lister** : enumere `campaigns/*.campaign.json` (nom + nombre d'actions).
- **24 Lancer** : selecteur interactif, execute la campagne contre l'API en
  cours, ecrit un rapport horodate dans `.run/campaigns/`.

**Nettoyage (25)** :

- **25 Purger** : arrete proprement lab/API/console, puis balaie les processus
  residuels `recette.api`, `recette.lab.mock_server` et vite **ancres dans ce
  repo uniquement** (verification du chemin dans les arguments du process).
  Ne touche **jamais** un container Docker ni un processus exterieur au repo.
  Nettoie les pid/port files et affiche les ports encore ecoutes pour controle.
  A utiliser quand un serveur local du projet est reste bloque ou que les pid
  files ont ete perdus.

---

## 3. CLI non interactif

Equivalents ligne de commande (memes sous-programmes) :

```
./recette.sh up|down|restart|rebuild|ps        # docker lab
./recette.sh logs [svc]|shell [svc]            # docker lab
./recette.sh status                            # snapshot global
./recette.sh api start|stop|restart|status|logs
./recette.sh platform up|down|restart|status|purge
./recette.sh console start|stop|status|logs
./recette.sh campaign list|run <nom> [--json]
./recette.sh test|gates|report|validate|run|discovery [--docker]
./recette.sh git status|pull|push|sync|branches|clean-merged
./recette.sh --help
```

`campaign run` accepte un nom court (`identity-offboarding`), un nom de fichier
ou un chemin ; `--json` ecrit le rapport dans `.run/campaigns/`.

---

## 4. Parcours type (de zero a une approbation)

```
./recette.sh platform up
./recette.sh console start
```

Puis ouvrir `http://localhost:5173` (onglet **Cockpit**) :
1. onglet **Agents** : creer un agent (id, principal, target_system, goal,
   capability_scope = actions canoniques) ; optionnellement un ai-backend.
2. onglet **Cockpit** : choisir l'agent, mode **mock**, **Lancer** -> le flux
   live affiche chaque etape (`step read_repo -> github`), puis `end completed`.
3. onglet **Recette** : **Lancer discovery** et **Lancer identification** ->
   scorecards detecte/distingue vs ground-truth.
4. onglet **Campagnes** : creer une campagne (cocher des agents), **Lancer**,
   puis **Replay** sur un enregistrement -> verdict IDENTIQUE (determinisme I4).

> Deux notions de "campagne" coexistent : l'onglet **Campagnes** du cockpit
> (campagnes de recette discovery, agents Lane B persistes + replay, via l'API
> `/campaigns`) et la CLI `./recette.sh campaign` (anciennes campagnes de
> gouvernance = actions allow/deny/escalate, `campaigns/*.campaign.json`).
> La premiere est le chemin courant ; la seconde est conservee pour la
> plateforme de gouvernance (mock).

A la fin :

```
./recette.sh platform down      # arret propre
./recette.sh platform purge     # si un serveur est reste bloque
```

---

## 5. Ports et pourquoi `:8094/` renvoie `{"detail":"Not Found"}`

| Service | Port par defaut | Note |
|---------|-----------------|------|
| API gouvernee | 8090 (ou 1er libre 8090-8099, voir `.run/api.port`) | API JSON, **pas** une page web |
| lab mock | 8082 | `GET /healthz` uniquement |
| console UX | 5173 | **c'est ici l'interface graphique** |
| docker discovery-mock | 8081 | lab historique |

L'API n'a pas de page racine : `GET /` renvoie `404 {"detail":"Not Found"}`,
c'est normal. Les routes utiles sont `/health`, `/actions/execute`,
`/approvals`, `/audit/...`, `/catalog/actions`, `/policies`. **L'UX
graphique est la console sur :5173**, pas l'API.

---

## 6. Configuration (R5 -- tout via env)

Surcharger n'importe quel defaut par variable d'environnement (defauts dans
`cicd/lib/common.sh`) :

| Variable | Defaut | Role |
|----------|--------|------|
| `INSPECT_IA_AGENTS_API_PORT` | 8090 | port API (sinon auto-pick) |
| `INSPECT_IA_AGENTS_LAB_PORT` | 8082 | port lab mock |
| `INSPECT_IA_AGENTS_CONSOLE_PORT` | 5173 | port console |
| `INSPECT_IA_AGENTS_PLATFORM_DATA` | `<repo>/data` | dossier event store |
| `INSPECT_IA_AGENTS_EVENT_STORE_PATH` | `<data>/inspect_ia_agents.events.db` | base SQLite d'audit |
| `INSPECT_IA_AGENTS_POLICIES_DIR` | `<repo>/config/policies` | versions de policy |

Pid/logs/rapports sous `.run/` : `api.pid`, `api.port`, `lab.pid`,
`console.pid`, `*.log`, `campaigns/*.json`.

Aucun secret n'est jamais stocke (R8) -- les credentials des systemes reels
viendraient de l'environnement, detenus par les proxies.

---

## 7. Liens

- Installation (prerequis + premier demarrage) : [installation.md](installation.md)
- Plateforme (docker lab + e2e) : [platform.md](platform.md)
- API Track U : [api.md](api.md)
- Catalogue 118 actions : [../tracking/PLAN_high-risk-action-catalog_2026-06-12.md](../tracking/PLAN_high-risk-action-catalog_2026-06-12.md)
