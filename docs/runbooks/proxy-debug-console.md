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
- Les traces vivent dans un ring borne en memoire (`RingTraceRecorder`). Le ring
  est une **vue jetable** -- la verite durable reste dans le log d'audit
  append-only (I1).
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

## API

| Methode | Chemin | Role |
|--------|------|---------|
| GET | `/proxy/debug` | `{debug_enabled, trace_count}` |
| GET | `/proxy/traces?tail=N` | traces enregistrees (les plus anciennes d'abord ; `tail` conserve les N dernieres) |
| DELETE | `/proxy/traces` | vide le buffer (le log d'audit est intact, I1) |

Exemple :

```
curl -s http://127.0.0.1:8080/proxy/debug
curl -s "http://127.0.0.1:8080/proxy/traces?tail=50"
curl -s -X DELETE http://127.0.0.1:8080/proxy/traces
```

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
| `tests/test_proxy_tracing.py` | le decorateur enregistre/retourne verbatim, fail-safe, ring borne, bascule par env |
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
- Buffer plein -> les traces les plus anciennes sont supprimees (ring borne) ;
  `seq` reste monotone ; le log d'audit reste complet.

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

La page `/proxy` a une bascule de source : **traces app** (la liste des
`ProxyTrace`) et **wire (mitmproxy)** (`WirePanel` : statut, liste de flows,
detail requete/reponse, clear). Lorsque l'overlay n'est pas configure, le panneau
montre comment l'activer plutot qu'une liste vide.

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
                     API POST /proxy/wire --> WireFlowRecorder (bounded ring, I1)
                             ^
                Proxy page <--GET /proxy/wire (status + flows)
```

- `recette/platform/proxy/wire.py` -- `WireFlow` + `WireFlowRecorder` (reflete le
  ring de traces : borne, `seq` monotone, jetable) + `normalize_flow` pur.
- `scripts/mitm_wire_addon.py` -- addon mitmdump : normalise chaque flow et le
  POST vers l'ingest de l'API (fail-safe, n'altere jamais le trafic).
- Endpoints : `POST /proxy/wire` (ingest), `GET /proxy/wire` (+ `tail`,
  `run_id`), `DELETE /proxy/wire`, `GET /proxy/wire/status`.

### Le demarrer (R19, jamais de lancement manuel)

```
./recette.sh wire up
export INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:8083
./recette.sh api restart
```

Les effets de bord de l'agent en mode lab (mock_local / declared_url) passent
alors par mitmproxy et apparaissent dans le panneau wire. `./recette.sh wire
down|status|logs` gerent le conteneur ; `wire ca` affiche le chemin de la CA.

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
| `tests/test_wire_proxy.py` | normalize/clamp de WireFlow, ring borne, seq monotone, immutabilite |
| `tests/test_api_wire.py` | endpoints `/proxy/wire*` ; ingest/list/clear/status ; tail ; run_id ; 422 |

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
Une jointure par `side_effect_hash` au niveau du flow (ghost via une cible
*allowlistee*) est la phase 3. Cela reste un LAB de recette : il *observe* le
chemin non mediatise, il n'*applique* pas de blocage reseau. Bloquer en dur le
chemin sortant direct (isolation reseau du pod, plus le handshake d'identite au
boot de I3) est le travail de la plateforme, pas de la simulation. Le lab prepare
et score ; l'enforcement est une couche separee.
| `tests/test_wire_routing.py` | couture proxy_url + ca_bundle ; threading de resolve_proxy ; env wire Slack |
| `tests/test_mitm_addon.py` | normalisation de flow de l'addon + gardes fail-safe (sans runtime mitmproxy) |
| `console/src/pages/proxy/WirePanel.contract.test.tsx` | contrat de panneau R16 (fixture reelle, active/desactive) |
