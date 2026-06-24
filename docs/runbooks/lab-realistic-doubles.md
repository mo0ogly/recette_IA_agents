# Doublures realistes du lab -- runbook

Le lab (`recette/lab/`, servi sur `:8082` et sous forme de serveurs `mock_local` sur
`9101`-`9112`) est le pendant simule des 16 systemes gouvernes contre lesquels un agent agit.
Chaque systeme est une doublure de domaine dans `recette/lab/domains/<system>.py` avec un unique
point d'entree `handle(action_type, resource, payload) -> dict | None`, dispatche
par `recette/lab/mock_server.py` sur `POST /{target_system}/execute`.

Une doublure n'est PAS un stub. Pour chaque action cataloguee elle retourne des champs
realistes, a la forme metier, valide son entree comme le ferait le vrai systeme, et
reste deterministe au byte pres pour que le replay (I4) tienne.

## Les trois dimensions de realisme (chaque domaine honore les trois)

1. **Succes a la forme metier** -- des champs par action que retourne une vraie API (un virement
   bancaire retourne un `transfer_id` + `value_date` + `status`, une policy de bucket
   retourne `bucket` + `acl` + `exposed`), pas `{"status": "simulated"}`.
2. **Validation d'entree -> 422** -- une action CONNUE appelee avec une entree INVALIDE (un
   montant negatif, un IBAN malforme, une reference de beneficiaire inconnue, une mauvaise devise) leve
   `LabActionError(422, msg, code=..., detail={...})`. Le mock server la mappe vers
   ce statut HTTP + une enveloppe d'erreur `{"success": false, "error": msg, "code":
   ..., "detail": {...}}`. `code`/`detail` sont optionnels et retrocompatibles : un
   raise message-seul fonctionne toujours et l'enveloppe omet les cles absentes.
3. **Coherence deterministe** -- toutes les valeurs derivees viennent d'un digest SHA-256
   de `(domain, action_type, resource, payload)` ; pas d'horloge, pas d'aleatoire, pas d'etat.
   Le meme appel produit toujours la meme reponse (I4).

## Le modele d'entite (coherence inter-appels sans etat)

`recette/lab/domains/_entities.py` est la couche d'entite deterministe. Une entite
(une facture, un compte, un fournisseur) est une fonction PURE de son id :
`derive_invoice("inv/9")` retourne la meme `Invoice` pour chaque action qui
touche `inv/9`, sur ce run et sur chaque replay. La coherence inter-appels ne necessite donc
AUCUN etat mutable (I4) : deux actions sur le meme id observent la meme entite parce que
toutes deux la recalculent depuis l'id seul.

Douze domaines l'adoptent : **finance, crm, hris, legal_dms, support_desk, cloud,
slack, product_cms, data_platform, github, gitlab, mcp**. Chacun obtient des reponses
plus riches, une coherence inter-appels, un listing de seed-discovery sur son action de lecture
(resource vide/`"all"`/`"*"`), des erreurs structurees (`code` + `detail`), et UN
rejet de machine a etats. L'etat bloquant est attribue UNIQUEMENT aux ids d'un
ensemble explicite de "blocking seed", de sorte qu'un id arbitraire (une sonde, un id de scenario frais)
reste toujours actionnable -- le rejet est demontre via l'id de seed.

| Domaine | Entite lue | Coherent a travers | Rejet blocking-seed (422) |
|---|---|---|---|
| finance | invoice | read/refund/validate/credit_note | `invoice_paid` -- rembourser une facture PAID (utiliser credit_note) |
| crm | contact | change_opportunity_amounts / change_account_owner | `opportunity_closed` -- changer le montant d'une opportunite closed_won |
| hris | department / employee | salary/leave/contract/access sur un employe | `employee_terminated` -- modify_salary/modify_leave sur un employe licencie |
| legal_dms | policy / document | delete/share sur un document | `legal_hold` -- supprimer un document sous legal hold |
| support_desk | ticket | modify/reply/delete sur un ticket | `ticket_closed` -- modify_critical_ticket_status sur un ticket ferme |
| cloud | resource | delete/modify sur une ressource | `instance_terminated` -- delete/modify une ressource terminee |
| slack | channel | read/post/delete sur un channel | `channel_archived` -- poster vers/supprimer un channel archive |
| product_cms | content | read/publish/edit/delete sur un contenu | `content_archived` -- publish/edit/delete un contenu archive |
| data_platform | dataset | query/export/download sur un dataset | `dataset_frozen` -- query/export un dataset gele |
| github | repository | read/deploy/merge/delete sur un repo | `repo_archived` -- deploy/merge/delete un repo archive |
| gitlab | project | read/push/merge sur un projet | `project_archived` -- push/merge vers un projet archive |
| mcp | tool | invoke un tool | `tool_disabled` -- invoke un tool non enregistre/desactive |

Notes :
- `result_id` garde sa recette par action `sha256("<domain>:<action>:<resource>:<payload>")[:12]` ;
  le modele d'entite utilise un digest SEPARE indexe sur l'id, donc la coherence ne
  perturbe pas `result_id` (la suite de tests asserte la recette).
- Le temps est un ordinal relatif (par ex. `due_in_days`), jamais une date d'horloge murale, donc
  le modele reste byte-stable au replay.
- Un id arbitraire derive quand meme une entite valide (n'importe quel id fonctionne) ; les ids de seed derivent
  une entite plus riche / bloquante. La discovery n'ajoute jamais une NOUVELLE action gouvernee (une nouvelle action
  necessiterait une entree au catalogue -> refusee par la gateway).
- Le D2 du coverage guard traite une `LabActionError` levee comme GEREE (le
  contrat a trois issues : dict / None / raise).

## La boite a outils (ne pas reinventer par domaine)

- `recette/lab/errors.py` -- `LabActionError(status_code, message)`. La troisieme
  issue du handler (a cote de dict=succes et None=action inconnue -> 404).
- `recette/lab/domains/_realism.py` -- helpers deterministes partages :
  - `digest(domain, action_type, resource, payload)` -> sha256 hex (le seed).
  - `ref(prefix, dig)` -> id stable comme `TRF-1a2b3c4d`.
  - `pick(dig, choices)` -> choix deterministe dans un tuple.
  - `derived_int(dig, lo, hi)` -> int deterministe dans `[lo, hi]`.
  - `coerce_positive_number(raw)` -> float ou None (accepte les chaines numeriques,
    rejette les ordures comme `"payment_amount"`) ; a utiliser pour la validation de montant.
  - `valid_email(value)` -> bool.
  - `envelope(action_type, resource, dig)` -> la base commune `{action, resource,
    result_id}` que chaque succes etend.

## Les trois issues du handler

| Issue | Le handler retourne | Mock server -> |
|---|---|---|
| Succes | `dict` (champs metier) | `200` + `{"success": true, "data": ...}` |
| Action connue, mauvaise entree | `raise LabActionError(422, msg)` | `422` + `{"success": false, "error": msg}` |
| Action inconnue | `None` | `404` |

## Les 16 domaines

`recette/lab/domains/__init__.py::HANDLER_MODULES` est le registre :
`cloud, comms, compliance, crm, data_platform, finance, github, gitlab, hris,
knowledge_base, legal_dms, mcp, okta, product_cms, slack, support_desk`.

Ces 16 correspondent aux 16 systemes gouvernes du catalogue. Douze portent un serveur
`mock_local` dedie (`:9101`-`:9112`) : cloud, finance, github, gitlab, hris,
knowledge_base, legal_dms, mcp, okta, product_cms, slack, support_desk. Les
quatre autres (comms, compliance, crm, data_platform) sont des doublures de lab servies uniquement
par le `LabForge` in-process / le lab partage `:8082`, sans serveur
mock_local autonome.

`github`/`gitlab` gardent les handlers de lecture git canoniques (`read_repo`,
`list_repos`, ...) et enrichissent les actions d'ecriture risquees. `knowledge_base`
preserve le chemin de query de doc empoisonne utilise par la recette RAG
(`rag-knowledge-base-crud.md`).

## Reload apres un changement de domaine (gotcha operationnel)

Un serveur `mock_local` est un sous-processus demarre une fois. Editer un handler de domaine
ne le hot-reload PAS -- un sous-processus perime continue de servir l'ancien code. Apres
tout changement de domaine, reload le serveur :

```
curl -s -X POST http://localhost:8090/config/servers/<id>/stop
curl -s -X POST http://localhost:8090/config/servers/<id>/start
```

`./recette.sh platform up` demarre un ensemble frais, donc un redemarrage complet recupere aussi
les changements. Ne jamais hand-launch un serveur (R19).

## Tester une action a la main

```
curl -s -X POST http://localhost:8082/finance/execute -H 'content-type: application/json' -d '{"action_type":"launch_wire_transfer","resource":"acct/ops","payload":{"amount":"4200","currency":"EUR","payee":"ACME Ltd"}}'
```

Une mauvaise entree retourne 422, par ex. `payload.amount = "payment_amount"` ->
`{"success": false, "error": "..."}`. Depuis la console c'est le panneau Servers ->
Test (`ServerTestPanel.tsx`).

## Campagnes composees sur ces doublures

`campaigns/multidomain/*.campaign.json` composent les agents par domaine en
scenarios multi-agents gouvernes : `ops-readonly-sweep` (lectures sur chemin allow),
`insider-exfil-chain` (escalate + deny sur suppression de preuve), `prod-sabotage`
(deny-by-default), `collab-content-day` (allow + escalate), `incident-response-
bridge` (lectures SOC + escalate du containment), `release-train` (lectures devops +
escalate des deploys + deny du backup-delete), `finance-approval-bridge`. Ils s'executent
a travers la vraie gateway et assertent les verdicts par action :

```
.venv/bin/python scripts/run_multidomain_scenarios.py     # ALL PASS -- 7 campaigns
```

Le harnais superpose en memoire les actions de lecture de la famille git gitlab UNIQUEMENT si le
catalogue committe ne les definit pas deja (il defere a un domaine gitlab committe quand il en
existe un), et leur accorde ALLOW pour `devops_admin` ; tout le
reste utilise la baseline du catalogue committe. Le verdict est la ground truth -- un
mismatch signifie que le mapping de policy est faux, ne jamais affaiblir l'`expect`.

## Campagne d'orchestration macro (lien campagne <-> equipe MAF)

Une campagne peut porter un bloc `links` qui la lie a une equipe d'orchestration MAF
(`corpus/maf_orchestration/`) sur une `shared_action` dont le human gate (I6) doit etre
honore des deux cotes -- une **campagne d'orchestration macro**. L'equipe PLANIFIE le gate
(un tool `approval=always` qu'elle approuve avant usage) ; la gateway l'IMPOSE (la
meme action escalate vers pending). `finance-approval-bridge` se lie a
`finance-approval-handoff-correct` sur `launch_wire_transfer`.

```json
"links": [{ "kind": "maf_orchestration", "team": "finance-approval-handoff-correct",
            "shared_action": "launch_wire_transfer", "invariant": "I6", "note": "..." }]
```

Le lien est de la donnee, pas du code : le harnais le decouvre depuis les fichiers de campagne,
juge l'equipe, lance la campagne, et asserte que l'action partagee escalate :

```
.venv/bin/python scripts/run_orchestrated_campaign.py     # ALL PASS -- N macro orchestration campaigns
```

Sur la console cela apparait sur la page recette-campaigns (un badge `orchestration`
sur la ligne, un onglet Orchestration dans la modal Expliquer). Les deux harnais
sont aussi gardes par `tests/test_orchestrated_campaigns.py` pour qu'une regression de verdict
fasse echouer `./recette.sh test`, pas seulement la CLI.

## Gate de determinisme

Chaque handler est une fonction pure de ses entrees (I4). Pas de `time`/`datetime.now`/
`random` dans aucune doublure de domaine. Le chemin d'erreur est deterministe lui aussi : le meme
appel invalide leve toujours le meme statut + message. Voir
`.claude/rules/determinism-replay.md`.

## Injection de fautes INFRA (chaos) -- recette des failure-modes

Par defaut le lab repond 200 (succes metier) ou 4xx metier (`LabActionError`, ex.
422 entree invalide, facture deja payee). Il ne tombait JAMAIS en panne INFRA --
donc toute la spec `.claude/rules/failure-modes.md` (une dependance down => l'agent
doit FREEZE/retry, jamais executer en optimiste, I5/I6) etait non-recettable : une
dependance fiable a 100% n'exerce jamais le comportement fail-safe.

`recette/lab/chaos.py` ajoute une couche de fautes INFRA **deterministe** (I4) et
**off par defaut** (R5 config-first), activee par `INSPECT_IA_AGENTS_LAB_CHAOS`
(JSON inline OU chemin vers un fichier JSON) :

```json
{
  "seed": "rec-2026-06-24",
  "systems": {
    "okta":    {"error_rate": 0.25, "statuses": [429, 503]},
    "finance": {"error_rate": 0.5,  "statuses": [503, 504]},
    "*":       {"error_rate": 0.1,  "statuses": [503]}
  }
}
```

- `error_rate` (0..1, clampe) = fraction des requetes d'un systeme qui faute.
- `statuses` = le pool de statuts INFRA injectables : **429** rate-limit, **503**
  service unavailable (couvre aussi un reset de connexion vu par l'appelant),
  **504** upstream timeout. Le timeout est MODELISE en 504 **sans `sleep` reel**,
  donc la suite deterministe reste rapide et byte-stable -- une vraie latence
  appartient a un mode live, jamais au chemin de decision/juge.
- `"*"` = defaut applique a tout systeme sans entree explicite. Un systeme sans
  entree et sans `"*"` ne faute jamais.

**Determinisme (I4)** : la decision de faute est une fonction PURE de
`(seed, event_id, target_system, action_type)` -- ni horloge ni aleatoire. Le meme
event logique faute (ou non) a l'identique, et le statut choisi est stable. Comme
`event_id` est derive d'une sequence dans ce systeme, le motif de faute est
reproductible d'un run a l'autre (donc rejouable pour un chercheur). Une config
chaos malformee retombe sur OFF (le lab doit toujours servir), jamais un crash.

Le hook est dans `mock_server.py` : la faute court-circuite AVANT `dispatch`, donc
l'agent voit un 429/503/504 et doit emprunter son chemin fail-safe. Tests :
`tests/test_lab_chaos.py` (11 cas : off-par-defaut, clamp, determinisme, split
partiel, choix de statut). Preuve live : un POST okta sous `error_rate:1.0`
retourne HTTP 503 enveloppe `service_unavailable` ; un systeme a `error_rate:0`
passe en 200.

## Liens connexes

- `docs/ARCHITECTURE.md` -- topologie du lab + diagrammes du chemin gouverne.
- `docs/runbooks/platform.md` -- cycle de vie gateway + lab.
- `docs/runbooks/recette-sh.md` -- le lanceur unique (R19).
- `.claude/rules/failure-modes.md` -- comportement fail-safe attendu sous faute INFRA.
- `.claude/skills/recette-campaign-builder/` -- comment un verdict de campagne est decide.
