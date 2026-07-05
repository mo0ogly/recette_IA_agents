# Runbook -- Console de debug du proxy (tracage des effets de bord, I5)

Le proxy d'effets de bord est le seul chemin de la logique d'un agent vers un
systeme externe (invariant I5). Ce runbook couvre la couche de **tracage de
debug** qui enregistre chaque `execute()` du proxy et la **console Monaco** qui
l'affiche, ainsi que le cablage **real_saas** qui permet a un run de s'executer
contre une forge reelle allowlistee.

## Ce que ca fait

- Un `TracingProxy` decore N'IMPORTE QUEL `ExternalSystemProxy` (lab ou reel) et
  enregistre un `ProxyTrace` par `execute()` : l'intention de la requete (event
  id, agent, action, systeme cible, ressource, payload) et le resultat (`ok`,
  code de statut, `side_effect_hash`, erreur).
- Les traces vivent dans le store SQLite de debug (`SqliteTraceRecorder` sur
  `SqliteProxyStore`, retention par prune). C'est une **vue jetable** -- la
  verite durable reste dans le log d'audit append-only (I1).
- La console (`/proxy`) affiche les traces en lecture seule dans Monaco : une
  liste a gauche, un inspecteur JSON / flux JSONL a droite.

Determinisme (I4) : une trace ne porte aucune valeur d'horloge murale propre.
L'ordre vient d'un `seq` monotone ; `timestamp` est l'horloge logique deja
capturee de l'evenement.

## L'activer (parametrable, R5)

Le tracage est desactive par defaut (zero surcout). Activez-le avec une variable
d'environnement lue au demarrage de l'app :

```
INSPECT_IA_AGENTS_PROXY_DEBUG=on
```

Valeurs truthy : `1`, `true`, `yes`, `on` (insensible a la casse). Toute autre
valeur est consideree comme desactivee. Lorsque c'est desactive, le proxy
s'execute normalement et **rien n'est enregistre** -- la console affiche une
banniere le signalant plutot qu'une liste vide qui ressemblerait a un etat
stable.

## Ce qui est trace

Deux chemins alimentent le meme recorder partage :

1. **Chemin gateway** -- `POST /actions/execute` (et l'execution pilotee par
   approbation). Le proxy d'effets de bord de la gateway est wrappe a la
   construction de l'app.
2. **Chemin agent Lane B** -- un agent enregistre lie a une entree `server`
   execute ses tool calls via `ProxyForge` ; ce proxy resolu est wrappe lui
   aussi. Ainsi les effets de bord d'un agent reel apparaissent dans la console.

Un agent **sans** liaison `server` utilise le `LabForge` en memoire, qui ne
produit aucun effet de bord externe et n'est donc pas trace.

## Le store SQLite de debug (retention, persistance, fail-safe)

Les deux buffers (traces app ET flows wire) vivent dans UNE base SQLite
(`SqliteProxyStore`, deux tables, compteurs `seq` independants) qui remplace
les anciens rings memoire :

| Variable | Defaut | Role |
|----------|--------|------|
| `INSPECT_IA_AGENTS_PROXY_DB` | `.run/proxy_traces.db` | chemin du fichier SQLite |
| `INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS` | `50000` | plafond de retention PAR TABLE (`<= 0` desactive le prune ; valeur illisible -> defaut, fail-safe) |

- **Retention par prune amorti** : apres un insert committe dont le rowid tombe
  sur la cadence de prune, les lignes les plus anciennes au-dela de `max_rows`
  sont supprimees. Un echec de prune est logge et avale (l'insert est deja
  committe) et ne positionne jamais `store_error`.
- **Persistance au redemarrage** : le fichier survit a un restart de l'API --
  une longue campagne garde ses traces. Les curseurs client se resynchronisent
  via `reset` (voir le contrat delta-poll ci-dessous).
- **Hash a l'insert (wire)** : le `side_effect_hash` d'un flow gouverne est
  calcule UNE fois a l'insert et persiste en colonne -- `GET /proxy/wire` le
  lit, il ne le recalcule plus a chaque appel.
- **Fail-safe `store_error`** : un store casse (disque plein, base corrompue)
  ne bloque JAMAIS l'execution (I5) -- l'enregistrement echoue, la trace / le
  flow est perdu (c'est un buffer de debug), le message de panne est surface
  dans `store_error` sur `GET /proxy/debug` (la console signale le buffer
  degrade), et il est efface au prochain insert reussi.
- **DELETE garde sa semantique de purge** : `DELETE /proxy/traces` /
  `DELETE /proxy/wire` vident la table de debug ; `seq` reste monotone
  (AUTOINCREMENT survit au DELETE) ; le log d'audit append-only est intact
  (I1). Ce store est le buffer de DEBUG, jamais l'event store.

## API

| Methode | Chemin | Role |
|--------|------|---------|
| GET | `/proxy/debug` | `{debug_enabled, trace_count, store_error}` (`trace_count` = COUNT SQL, jamais un snapshot complet ; `store_error` = derniere panne du store, `null` si sain) |
| POST | `/proxy/debug` | bascule le tracage a chaud `{enabled: bool}` -> `{debug_enabled}` (action operateur, loggee via tracing, jamais ecrite dans l'event store ; 422 si non-bool) |
| GET | `/proxy/traces` | delta-poll : `since_seq` (curseur) + filtres serveur `run_id`/`agent_id`/`target`/`outcome`/`q` + `limit` (`tail` en compat) -> enveloppe `{debug_enabled, traces, last_seq, total, reset}` |
| DELETE | `/proxy/traces` | vide le buffer (le log d'audit est intact, I1) |
| GET | `/proxy/sessions/delta` | poll coalesce du panneau sessions : traces + wire + reconcile en UN appel (voir ci-dessous) |

Exemple :

```
curl -s http://127.0.0.1:8080/proxy/debug
curl -s -X POST http://127.0.0.1:8080/proxy/debug -H 'Content-Type: application/json' -d '{"enabled":true}'
curl -s "http://127.0.0.1:8080/proxy/traces?since_seq=42&outcome=fail&limit=100"
curl -s -X DELETE http://127.0.0.1:8080/proxy/traces
```

### Contrat delta-poll (since_seq / last_seq / total / reset)

`GET /proxy/traces` et `GET /proxy/wire` partagent le meme contrat de poll
incremental, evalue en SQL (jamais un snapshot complet re-filtre en Python) :

- `since_seq` : curseur client ; seules les lignes strictement plus recentes
  sont renvoyees (delta ascendant, les plus anciennes d'abord).
- `last_seq` : MAX(seq) NON filtre de la table -- le prochain curseur du client.
- `total` : compte du jeu FILTRE en ignorant `since_seq`/`limit`/`tail` (les
  compteurs d'en-tete sans charger les lignes).
- `reset` : vrai quand le curseur client est EN AVANCE sur le serveur (buffer
  vide par DELETE ou store recree) ; le serveur re-sert alors la selection
  complete SANS curseur et le client se resynchronise en un seul aller-retour.
- `limit` conserve les N premieres lignes du delta ascendant ; `tail` (compat)
  conserve les N dernieres, gagne sur `limit` et ignore `since_seq`.

Filtres serveur par endpoint (combines en AND ; `q` = sous-chaine insensible a
la casse) :

| Endpoint | Filtres |
|----------|---------|
| `GET /proxy/traces` | `run_id`, `agent_id`, `target`, `outcome` (`ok` \| `fail`, toute autre valeur -> 422), `q` (action_type + resource + request_payload + response) |
| `GET /proxy/wire` | `run_id`, `host`, `method`, `status`, `q` (path + bodies) |

Les badges du menu de sources sont alimentes par les endpoints de statut
LEGERS (`GET /proxy/debug` -> `trace_count`, `GET /proxy/wire/status` ->
`flow_count`, `GET /proxy/reconcile/status` -> `{ok, bypass_count}`) : des
COUNT SQL, jamais le payload complet.

### GET /proxy/sessions/delta -- le poll coalesce du panneau sessions

Remplace les trois requetes paralleles par tick du panneau sessions
(`/proxy/traces` + `/proxy/wire` + `/proxy/reconcile`) par UN aller-retour :

```
GET /proxy/sessions/delta?since_seq=..&wire_since_seq=..&run_id=..&strict=true
-> {debug_enabled, traces, last_seq, reset,
    wire_flows, wire_last_seq, wire_reset,
    reconcile: {run_id, strict, ...}}
```

- Curseurs INDEPENDANTS par cote : `since_seq` pour les traces,
  `wire_since_seq` pour le wire -- chacun avec la meme semantique `reset` que
  les endpoints par source ; un curseur perime d'un cote ne force jamais la
  resynchro de l'autre.
- Asymetrie `run_id` VOULUE (miroir exact du panneau) : `run_id` ne scope que
  le delta WIRE et la jointure reconcile ; les traces restent NON filtrees (le
  panneau groupe toutes les traces cote client).
- `strict` vaut `true` par defaut (la jointure stricte par hash au niveau du
  flow ; `reconcile` porte la meme forme que `GET /proxy/reconcile`).
- Pas de `tail`/`limit` (le panneau ne s'en sert pas) ; les deux vues passent
  par la redaction ; lecture seule (I1).
- Le reconcile prend ses PROPRES snapshots du recorder : un nouveau flow wire
  peut apparaitre dans le badge reconcile un tick de poll avant le delta wire
  -- benin, se resorbe au tick suivant.

Le `POST /proxy/debug` permet de **basculer le tracage depuis l'UI** (interrupteur
dans le sous-header de la source "traces app") sans redemarrer l'app : il bascule
a la fois le drapeau `app.state` et le `TracingProxy` vivant (`set_enabled`). La
valeur par defaut au boot reste celle de `INSPECT_IA_AGENTS_PROXY_DEBUG` (R5).

## Cablage real_saas

Le `router` du proxy (`resolve_proxy`) est pur : il ne lit aucune variable
d'environnement et ne detient aucun credential, donc une entree de serveur
`real_saas` levait une `ValueError` par defaut. Il accepte desormais un
`real_proxy_factory` injecte :

- `recette/platform/proxy/real_proxy.py` fournit `RealForgeProxy` (adapte une
  forge a `ExternalSystemProxy.execute`) et
  `build_real_proxy_factory(*, enable_writes=False)`.
- La factory construit une forge reelle **allowlistee** a partir de
  l'environnement (`recette.realmode.build_real_forge`) : token via
  `INSPECT_IA_AGENTS_<SYSTEM>_TOKEN`, allowlist via
  `INSPECT_IA_AGENTS_REAL_ALLOWLIST`, ecritures desactivees sauf activation
  explicite (R8).

Fail-safe (failure-modes) : un rejet d'allowlist, une ecriture bloquee, un SDK
manquant ou toute erreur de forge est mappe sur `ExecutionResult(ok=False, ...)`
-- le proxy ne leve jamais a travers la gateway et ne se rabat jamais sur la
mauvaise cible (I5).

Cablez-le sur un call-site impur :

```python
from recette.platform.proxy.router import resolve_proxy
from recette.platform.proxy.real_proxy import build_real_proxy_factory

proxy = resolve_proxy(
    agent, servers, default_proxy,
    real_proxy_factory=build_real_proxy_factory(enable_writes=False),
)
```

Le lab reste le defaut partout ; le mode reel est opt-in et ne touche jamais que
des orgs de test allowlistees.

## Tests

| Test | Prouve |
|------|--------|
| `tests/test_proxy_tracing.py` | le decorateur enregistre/retourne verbatim, fail-safe, bascule par env (la retention vit desormais dans le store) |
| `tests/test_proxy_store.py` | store SQLite : mapping golden-field, `store_error` (panne -> jamais levee, recovery), hash-at-insert wire, requetes delta/filtres/tail, clear + `seq` monotone |
| `tests/test_api_proxy_sessions_delta.py` | `GET /proxy/sessions/delta` : snapshot complet sans curseurs, deltas incrementaux, `run_id` scope wire pas traces, resets independants, `strict` par defaut, redaction |
| `tests/test_real_proxy.py` | succes -> hash ; erreurs allowlist/ecriture/forge -> fail-safe |
| `tests/test_proxy_router.py` | real_saas utilise la factory injectee ; pas de factory -> erreur (compat ascendante) |
| `tests/test_api_proxy_traces.py` | endpoints `/proxy/*` ; debug on/off ; tail ; clear |
| `tests/test_api_proxy_traces_lane_b.py` | les effets de bord d'un agent Lane B REEL sont traces (debug on) / pas (off) |
| `console/src/pages/proxy/*.test.{ts,tsx}` | helpers de modele + contrat de page R16 contre une fixture reelle |

## Modes de defaillance

- Exception d'enregistrement -> avalee ; `execute()` retourne toujours le
  resultat wrappe (l'observabilite ne doit jamais casser le chemin I5).
- Debug desactive -> aucun enregistrement, aucune donnee dans la console,
  banniere affichee.
- Retention atteinte -> les lignes les plus anciennes sont prunees
  (`INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS`) ; `seq` reste monotone ; le log
  d'audit reste complet.
- Store SQLite casse -> l'execution n'est JAMAIS bloquee : la trace / le flow
  est perdu (buffer de debug), la panne est surfacee via `store_error` sur
  `GET /proxy/debug` et effacee au prochain insert reussi.

## Overlay d'interception du fil (mitmproxy) -- la vue au niveau reseau

Le `ProxyTrace` ci-dessus est la vue **au niveau applicatif** (l'intention de
l'agent a la frontiere `ExternalSystemProxy`). L'**overlay du fil** ajoute la vue
**au niveau reseau** : les octets reellement sur le fil du trafic agent -> cible,
captures par un vrai proxy d'interception (**mitmproxy**) tournant comme overlay
Docker OPTIONNEL. Deux altitudes du meme effet de bord I5.

Il est **desactive par defaut** et constitue une SURCHARGE, jamais un
remplacement : la recette deterministe ne passe jamais par lui (I4 inchange), le
`TracingProxy` maison reste le defaut.

### Dans l'UX

La page `/proxy` est pilotee par un registre de sources (menu en tete, deep-link
`?source=`). Quatre sources read-only :

- **traces app** -- la liste des `ProxyTrace` (intention + reponse), filtres
  agent/target/run, viewer Monaco, + un **interrupteur d'enregistrement** (POST
  `/proxy/debug`, remplace l'ancienne banniere passive).
- **wire (mitmproxy)** -- `WirePanel` : statut, liste de flows, detail
  requete/reponse, clear, + un **bouton on/off de l'overlay** (POST
  `/proxy/wire/overlay`). Overlay non configure -> le panneau montre comment
  l'activer.
- **reconciliation** -- la jointure wire<->audit (voir plus bas).
- **sessions** -- les echanges agent<->serveur **groupes en sessions** (voir la
  section dediee ci-dessous).

En tete de page, un **mini-lanceur** (`LaunchPanel`) lance un agent runtime
configure (POST `/runs` lane_b) et bascule automatiquement sur la source
**sessions** preselectionnee sur ce run -- "lancer un agent et le voir live dans
le proxy" en un ecran. Depuis le cockpit, un bouton "Voir dans le proxy"
deep-linke un run vers sa session (`/proxy?source=sessions&run=<id>`).

### Vue sessions -- echanges groupes + fusion wire

La source **sessions** (`SessionsPanel`) regroupe les `ProxyTrace` en SESSIONS
selectionnables par cle (`run` / `agent` / `agent->target`). Le groupement est
PUR et deterministe (I4 : tri stable par `seq`, aucune horloge ; gere les runs
concurrents entrelaces dans le buffer global sans contamination croisee). Chaque
session liste ses echanges ; deplier un echange montre la paire **requete<->
reponse** (intention `action_type`+`resource`+`payload` ET reponse serveur), et
"JSON complet" ouvre la trace brute dans Monaco.

**Fusion wire** : quand l'overlay est actif, chaque echange dont les octets
reseau ont ete captures porte un badge **`wire (octets)`** ; clic -> les octets
bruts (method/host/path/status + bodies) dans Monaco. La jointure echange<->flow
se fait par le `side_effect_hash` canonique (cf. correlation par run ci-dessous).
Overlay eteint -> pas de badge, le reste de la vue est intact (degradation
gracieuse).

Live : poll delta coalesce **1s** -- UN `GET /proxy/sessions/delta` par tick
(traces + wire + reconcile, deux curseurs independants ; voir le contrat dans
la section API) au lieu de trois requetes paralleles. Quasi temps reel ; pas
de push SSE. Lecture seule de bout en bout (I1).

### Choisir la route de transport (selecteur de proxy)

Un **`ProxySelector`** partage permet a un operateur de choisir le transport que
prennent les effets de bord d'un agent -- **Direct (sans proxy)** ou **Wire
(mitmproxy)** -- depuis les fenetres qui ont une console reseau : le panneau wire
de `/proxy` et les **Logs reseau** par run (cockpit `AgentRunModal`). Il s'appuie
sur `GET`/`POST /proxy/route` ; la selection est conservee cote serveur (afin que
chaque console reflete la meme route active) et s'applique aux runs demarres
ensuite. Transport uniquement : la route ne change jamais la decision
(allow/deny/escalate) ni le log d'action enregistre (I4). S'appuie sur
`recette/platform/proxy/route.py` (`ProxyRouteRegistry`) ; les routeurs de run
transmettent le `wire_proxy_url` de la route active au runner. La route initiale
est `wire` lorsque `INSPECT_IA_AGENTS_WIRE_PROXY` est defini, sinon `direct`.

Le formulaire **AI backends** de la console (onglet Agents) porte egalement un
preset **LiteLLM gateway (local)** qui cree en un clic un backend
`openai_compat` pointant vers l'overlay LiteLLM (`http://127.0.0.1:4000`) ; voir
`llm-gateway-litellm.md`.

### Architecture

```
agent --(HTTP proxy)--> [mitmproxy container] --> lab / real system
                             | addon POSTs each flow
                             v
                     API POST /proxy/wire --> SqliteWireRecorder (bounded debug store, I1)
                             ^
                Proxy page <--GET /proxy/wire (status + flows)
```

- `recette/platform/proxy/wire.py` -- `WireFlow` + `normalize_flow` pur ; le
  buffer est `SqliteWireRecorder` (store.py : borne, `seq` monotone, jetable).
- `scripts/mitm_wire_addon.py` -- addon mitmdump : normalise chaque flow et le
  POST vers l'ingest de l'API (fail-safe, n'altere jamais le trafic).
- Endpoints : `POST /proxy/wire` (ingest), `GET /proxy/wire` (delta-poll :
  `since_seq` + filtres `run_id`/`host`/`method`/`status`/`q` + `limit`,
  `tail` en compat -> enveloppe `{enabled, proxy_url, flows, last_seq, total,
  reset}` ; chaque flow porte son `side_effect_hash` PERSISTE, calcule a
  l'insert, pour la fusion sessions), `DELETE /proxy/wire`,
  `GET /proxy/wire/status` (`flow_count` = COUNT SQL),
  `POST /proxy/wire/overlay {action: up|down}` (controle l'overlay depuis l'UI ;
  voir ci-dessous).

### Correlation au run (x-inspect-run-id)

Pour que les octets reseau se rattachent a un run/agent/session, le proxy lab
injecte l'en-tete de requete **`x-inspect-run-id`** (le `run_id` du run). L'addon
mitmproxy le lit et tague chaque `WireFlow` avec ce `run_id`. Cable :
`resolve_proxy(run_id=...)` -> `LabHttpProxy(run_id=...)` -> en-tete par defaut du
client HTTP. C'est une metadonnee de transport : elle n'entre pas dans le chemin
de decision (I4) et le lab ignore un en-tete inconnu. Ainsi `GET
/proxy/wire?run_id=` ne renvoie que les flows d'un run, et la reconciliation +
la fusion sessions correlent par run.

### Controle de l'overlay depuis l'UI (POST /proxy/wire/overlay)

Le bouton on/off du panneau wire appelle `POST /proxy/wire/overlay {action}` qui
execute `./recette.sh wire up|down`. **Deny par defaut** (fail-safe, R5) : l'API
ne lance docker QUE si `INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL` est truthy (sinon
403) ; action invalide -> 422 ; action operateur loggee via tracing (jamais dans
l'event store). HONNETE : le script DEMARRE/ARRETE le conteneur ; router le
trafic agent au travers exige encore que l'API tourne avec
`INSPECT_IA_AGENTS_WIRE_PROXY` (ou la route de transport `wire`, ci-dessous) +
confiance CA -- rapporte dans `next_step`.

### Le demarrer (R19, jamais de lancement manuel)

```
./recette.sh wire up
export INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:8083
./recette.sh api restart
```

Les effets de bord de l'agent en mode lab (mock_local / declared_url) passent
alors par mitmproxy et apparaissent dans le panneau wire. `./recette.sh wire
down|status|logs` gerent le conteneur ; `wire ca` affiche le chemin de la CA.

**Sans redemarrage** : le registre de route de transport porte deja une cible
`wire` (proxy_url `:8083`). Apres `./recette.sh wire up`, selectionner la route
`wire` (`POST /proxy/route {target:"wire"}` ou le `ProxySelector` dans l'UI)
suffit a router les runs DEMARRES ENSUITE a travers l'overlay -- pas besoin de
`INSPECT_IA_AGENTS_WIRE_PROXY` + restart pour le trafic HTTP du lab. (Le restart
+ env reste necessaire pour le HTTPS des systemes reels via la CA, ci-dessous.)

### HTTPS vers des systemes reels (real_saas)

mitmproxy dechiffre le HTTPS uniquement si le client fait confiance a sa CA :

```
export INSPECT_IA_AGENTS_WIRE_CA="$(./recette.sh wire ca)"
# SDK forges (PyGithub / python-gitlab) honour the standard env instead:
export HTTPS_PROXY=http://127.0.0.1:8083 REQUESTS_CA_BUNDLE="$(./recette.sh wire ca)"
./recette.sh api restart
```

- `StdlibHttpClient` a gagne une couture `ca_bundle` ; `RealSlackProxy` (Slack
  via StdlibHttpClient) passe par l'overlay + la CA depuis
  `INSPECT_IA_AGENTS_WIRE_*`.
- La verification TLS reste ACTIVEE -- la CA est **ajoutee**, jamais desactivee.

### Determinisme (I4)

L'overlay est DESACTIVE dans toute recette deterministe et ne se trouve jamais
dans le chemin de decision/replay. Un `WireFlow` ne porte aucune valeur
d'horloge murale ; l'ordre est le `seq` monotone du recorder, exactement comme
`ProxyTrace`.

### Preuve live

`scripts/smoke_wire.py` -- s'auto-skip sans Docker ; sinon il demarre l'overlay,
pilote une requete a travers lui vers le lab, et asserte que le flow atteint
`GET /proxy/wire`.

### Tests wire

| Test | Prouve |
|------|--------|
| `tests/test_wire_proxy.py` | normalize/clamp de WireFlow, immutabilite (retention + seq monotone : `test_proxy_store.py`) |
| `tests/test_api_wire.py` | endpoints `/proxy/wire*` ; ingest/list/clear/status ; tail ; run_id ; 422 |
| `tests/test_api_wire_overlay.py` | `POST /proxy/wire/overlay` : deny par defaut (403), 422 action invalide, ordre validation-avant-gate, subprocess mocke |
| `tests/test_wire_run_correlation.py` | `LabHttpProxy(run_id=...)` pose l'en-tete `x-inspect-run-id` ; `resolve_proxy(run_id=...)` le threade ; absent sinon |
| `tests/test_api_wire_session_hash.py` | `GET /proxy/wire` enrichit chaque flow d'un `side_effect_hash` (gouverne -> str, sinon null) -- la cle de fusion sessions |
| `tests/test_api_proxy_debug_toggle.py` | `POST /proxy/debug` bascule a chaud l'etat + le TracingProxy ; 422 non-bool |

### Reconciliation wire-vs-audit -- detecter un chemin non mediatise (ghost-agent)

Mettre les deux altitudes cote a cote transforme l'overlay en detecteur de la
menace "ghost agent" / shadow-AI : un agent non enregistre qui parle directement
a un systeme externe via du code natif, contournant l'`ExternalSystemProxy` (et
donc le plan Control). Un tel appel produit un **effet de bord reseau sans
evenement d'audit**.

Les deux vues le rendent visible :

- la **chaine d'audit** (log append-only, alimente par le `ProxyTrace`
  mediatise, I1/I5) est ce qui est passe *par* la gateway ;
- le **fil mitmproxy** est ce qui etait reellement *sur le reseau*.

Ainsi, chaque flow vu sur le fil devrait avoir un evenement mediatise
correspondant dans le log d'audit. Un flow wire **sans contrepartie d'audit**
(une cible non mediatisee au sein de son run) est un **chemin non mediatise** --
la faille -- et c'est le signal a remonter au plan Control.

Statut (implemente, allowlist + jointure scopee au run) :
`recette/platform/proxy/reconcile.py` joint la vue wire (`WireFlow`) avec la vue
d'audit (`ProxyTrace`) par `run_id` (`reconcile_run`) ; un flow vers une cible
non mediatisee (p. ex. le honeypot `shadow-db-sink` sur `:9113`) est signale
comme un bypass. Surface a `GET /proxy/reconcile` et dans la console (page Proxy,
onglet "reconciliation"). Prouve de bout en bout par le smoke live
`scripts/smoke_reconcile.py` (overlay mitmproxy actif -> la sonde ghost ecrit
directement sur `:9113` -> reconcile rapporte `ok:false` avec le bypass `:9113`)
et par les suites unitaires/contrat deterministes (`tests/test_reconcile.py`,
`test_api_reconcile.py`, `test_ghost_probe.py`, `ReconcilePanel.contract.test.tsx`).
La jointure par `side_effect_hash` au niveau du flow (ghost via une cible
*allowlistee*) est desormais IMPLEMENTEE (`reconcile_strict`, `GET
/proxy/reconcile?strict=true` + bascule "strict" sur le panneau) : chaque flow
gouverne vers une cible mediatisee doit aussi porter un `side_effect_hash`
correspondant a un `ProxyTrace`, sinon `bypass_reason=no_audit_event`. Cela reste
un LAB de recette : il *observe* le
chemin non mediatise, il n'*applique* pas de blocage reseau. Bloquer en dur le
chemin sortant direct (isolation reseau du pod, plus le handshake d'identite au
boot de I3) est le travail de la plateforme, pas de la simulation. Le lab prepare
et score ; l'enforcement est une couche separee.
| `tests/test_wire_routing.py` | couture proxy_url + ca_bundle ; threading de resolve_proxy ; env wire Slack |
| `tests/test_mitm_addon.py` | normalisation de flow de l'addon + gardes fail-safe (sans runtime mitmproxy) |
| `console/src/pages/proxy/WirePanel.contract.test.tsx` | contrat de panneau R16 (fixture reelle, active/desactive) |

## Toolkit expert-debug (cockpit de debug d'une comm agent)

Au-dela des vues, la console `/proxy` est un cockpit pour debugger une
communication d'agent. Tout est client-side, pur (I4) et lecture seule (I1) ;
les deux exceptions backend (latence, redaction) sont des transformations de
VUE qui ne touchent jamais le log d'audit.

### Poll delta 1s + listes virtualisees
- Les panneaux traces app / wire / sessions pollent en **delta 1s**
  (`useDeltaFeed` : premier fetch complet, puis `since_seq` par tick, merge
  pur cote client, resynchro automatique sur `reset`). Chaque tick ne
  transporte que les lignes NOUVELLES, pas le buffer entier.
- Les listes traces app et wire sont **fenetrees** (`VirtualList`, hauteur de
  ligne fixe) : seule la fenetre visible est rendue en DOM, un buffer de
  dizaines de milliers de lignes reste fluide.
- **Suivi intelligent** : quand l'operateur remonte dans la liste, le
  tail-follow se coupe et un badge compte ce qui arrive ("N nouvelles traces
  -- reprendre le suivi" / "N nouveaux flux -- reprendre le suivi") ; un clic
  ressaute au direct.
- Les badges du menu (compteurs par source) viennent des endpoints de statut
  COUNT (poll 5s), jamais du payload complet.

### Enregistrer, figer, exporter
- **Toggle d'enregistrement** (sous-header source "traces app") : `POST
  /proxy/debug {enabled}` -- start/stop a chaud, sans redemarrage.
- **Pause / Reprendre** (bouton page-level, badge `PAUSE`) : fige le poll des 3
  sources pour inspecter a froid ; le store backend continue d'enregistrer,
  Reprendre rattrape via le curseur delta.
- **Suivi (tail -f)** sur les listes traces app et wire : auto-scroll vers la
  derniere ligne (off quand en pause) ; voir le suivi intelligent ci-dessus.
- **Export** : `Export JSONL` sur toute source + `Export HAR` sur wire
  (importable devtools/Charles/Fiddler). Exporte le filtre courant.
- **Copy as curl** par flux wire / par echange : rejoue l'appel en un coller
  (echappement shell sur).

### Cibler les paquets d'interet
- **Filtres + recherche** : wire (host/method/status/run + texte dans
  path+bodies), traces app (agent/target/run/outcome + texte), sessions
  (groupement run/agent/target + texte). Les filtres wire et traces app sont
  evalues **cote serveur** (SQL indexe, voir le contrat delta-poll) ; changer
  une clause invalide le curseur et redemarre le feed. Les filtres sont
  **deep-linkables** dans l'URL (`/proxy?source=wire&host=...&q=...`),
  partageables.
- **Pretty-print** des bodies + indicateur de **taille (octets UTF-8)** +
  marqueur `(tronque)` quand le body a ete clampe.

### Voir le detail + correler
- **Latence** par echange : `WireFlow.duration_ms` (calcule par l'addon mitm) +
  barre waterfall. Metadata wall-clock sur la vue wire, jamais dans le juge (I4).
- **Diff** deux flux wire cote a cote (echec vs succes).
- **Redaction secrets** (defaut ON, `INSPECT_IA_AGENTS_PROXY_REDACT`) : masque
  `Bearer`/`ghp_`/`sk-`/`xox`/`AKIA` + `cle:valeur` connus sur `GET /proxy/wire`
  + `/proxy/traces`. Le log d'audit reste intact (I1), `side_effect_hash`
  preserve. Best-effort ; les receipts content-free restent la voie crypto.
- **Badge ghost / non-medie** sur un echange de session dont le flux wire n'a pas
  d'evenement d'audit (reconcile strict dans la session).

### Lire l'agent sur 3 altitudes (legibility-first)
Par echange dans la vue sessions : **DECLARE** (manifest : target/capability) /
**DECIDE** (l'action-log LLM : le tool choisi + le "pourquoi", via
`GET /runs/{id}/events`) / **FAIT** (intention applicative + reponse serveur +
octets wire). Voir `docs/screenshots/sim/proxy-three-altitude-decision.png`.

### Replay-diff (debug de regression, determinisme I4)
La 5e source **replay-diff** rejoue un recording deux fois et diffe les
action-logs : badge **IDENTIQUE (I4)** si byte-stable, sinon une ligne
left/right + `regression`. Preuve sur un vrai recording (`camp-pr.00.gh-pr-bot`)
dans `docs/screenshots/sim/proxy-replay-diff.png`.

### Persistance (long run)
Les traces et flux wire sont persistes dans le store SQLite de debug
(`INSPECT_IA_AGENTS_PROXY_DB`, defaut `.run/proxy_traces.db`) et survivent au
redemarrage de l'API ; retention par `INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS`
(defaut 50000 lignes par table, prune amorti des plus vieilles lignes). Un
long run garde donc ses paquets sans mecanisme de rotation JSONL. Convenance
debug, pas un second event store (I1) -- detail dans la section "store SQLite"
en tete de runbook.

### Captures de reference
- `proxy-sessions-launch.png` -- lancer un agent et atterrir sur sa session live.
- `proxy-toolkit-filter-pause.png` -- filtre texte + Pause.
- `proxy-three-altitude-decision.png` -- les 3 altitudes par echange.
- `proxy-replay-diff.png` -- replay-diff IDENTIQUE (I4) sur un recording reel.

### Differe (infra-gated, non construit -- honnete)
- **Source eBPF live dans la session** : besoin de `CAP_BPF` + une sonde ; le
  bridge `recording -> recette/surface` existe pour le chemin enregistre.
- **SSE `/proxy/stream`** : gotcha SSE-hang connu ; le poll delta 1s + pause
  couvrent le besoin. Poll reste le defaut deterministe.
