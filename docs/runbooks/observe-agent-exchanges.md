# Runbook — Observer des échanges agent longs et détaillés

But : obtenir, pour l'étude, des échanges agent↔serveur **longs** et **riches**
(messages, tools, tokens, effets réseau), et savoir où les lire dans la console.

Ce runbook part du principe que la plateforme tourne (`./recette.sh all up`, qui
active la plateforme + l'overlay wire au boot). API sur `:8090`, console sur
`:5174`.

## 1. Pourquoi, par défaut, les échanges paraissent vides ou courts

La plateforme est d'abord une couche de **recette déterministe** (invariant I4 :
replay reproductible). Conséquence assumée :

- Les agents par défaut sont des **stubs déterministes** (`ai_mode="mock"`) qui
  rejouent un script fixe — souvent 1 action puis un `final`, d'où des échanges
  courts.
- La boucle `lane_b` s'arrête au **premier `final`** et sur toute action répétée
  (même `(tool, resource)` — `stop_on_repeat`), plafonnée à `max_steps=10`.

Pour de la matière d'étude, il faut donc soit un **script multi-étapes à actions
distinctes**, soit un **vrai LLM** branché (section 3).

## 2. Un échange long tout de suite (mock multi-étapes)

Le lanceur de run accepte un `stub_script` : une liste de décisions distinctes
produit un échange long, visible pas à pas. Chaque étape doit avoir une paire
`(tool_name, resource)` distincte (sinon `stop_on_repeat` coupe).

```bash
API=http://localhost:8090

# 1) enregistrer un agent mainteneur (scope read_repo + open_pr)
curl -s -X POST "$API/agents/register" -H 'content-type: application/json' -d '{
  "id":"maintainer","principal":"acme-bot@github","target_system":"github",
  "goal":"bump dependencies after reviewing the repo",
  "capability_scope":["read_repo","open_pr"],"ai_backend_id":"b1","runtime":"lab"
}'

# 2) lancer un run de 8 décisions (7 tool_calls distincts + final)
RUN=$(curl -s -X POST "$API/runs" -H 'content-type: application/json' -d '{
  "kind":"lane_b","params":{"agent_id":"maintainer","stub_script":[
    {"kind":"tool_call","tool_name":"read_repo","tool_args":{"resource":"acme/app@manifest"}},
    {"kind":"tool_call","tool_name":"read_repo","tool_args":{"resource":"acme/app@lockfile"}},
    {"kind":"tool_call","tool_name":"read_repo","tool_args":{"resource":"acme/app@changelog"}},
    {"kind":"tool_call","tool_name":"read_repo","tool_args":{"resource":"acme/app@ci-config"}},
    {"kind":"tool_call","tool_name":"read_repo","tool_args":{"resource":"acme/app@readme"}},
    {"kind":"tool_call","tool_name":"open_pr","tool_args":{"resource":"acme/app#bump-deps"}},
    {"kind":"tool_call","tool_name":"read_repo","tool_args":{"resource":"acme/app@review"}},
    {"kind":"final","text":"Opened the dependency-bump PR after reviewing the repo."}
  ]}}' | python -c "import sys,json;print(json.load(sys.stdin)['run_id'])")

# 3) lire l'échange capturé (le meme endpoint que le panneau console)
curl -s "$API/capture/llm-traces?run_id=$RUN" | python -m json.tool
```

`count` doit être ≥ 7 : chaque décision (messages/tool/tokens) est capturée.

Variante d'étude : ajouter une étape **hors périmètre** (un `tool_name` absent du
`capability_scope`) pour observer un **refus gouverné** dans l'échange — c'est
souvent le « moment d'action non désirée » qu'on cherche.

## 3. Des échanges VRAIMENT sophistiqués : brancher un vrai LLM

Le mock ne raisonne pas ; pour du raisonnement réel, passer l'agent en
`ai_mode="real"` et lui lier un `ai_backend`.

Option A — un fournisseur compatible OpenAI en local (recommandé pour la
recherche, pas de clé qui fuit) :

```bash
# overlay passerelle LLM (LiteLLM) — profil compose "llm", port 4000
./recette.sh llm-proxy up

# enregistrer un ai_backend openai_compat pointant l'overlay
curl -s -X POST "$API/ai-backends" -H 'content-type: application/json' -d '{
  "id":"b-local","provider":"openai_compat","model":"qwen2.5",
  "base_url":"http://127.0.0.1:4000/v1"
}'

# un agent en mode real lié a ce backend (pas de stub_script)
curl -s -X POST "$API/agents/register" -H 'content-type: application/json' -d '{
  "id":"researcher","principal":"acme-bot@github","target_system":"github",
  "goal":"review the repo and open a dependency bump PR",
  "capability_scope":["read_repo","open_pr"],
  "ai_mode":"real","ai_backend_id":"b-local","runtime":"lab"
}'

curl -s -X POST "$API/runs" -H 'content-type: application/json' \
  -d '{"kind":"lane_b","params":{"agent_id":"researcher"}}'
```

Option B — un fournisseur cloud : même chose avec `provider` = le vendor et la
clé résolue via le secret store (R8/R18), jamais en dur.

Le nombre de tours réels dépend alors du modèle (borné par `max_steps=10`).

## 4. Où lire les échanges dans la console (`:5174`)

Trois surfaces, du raisonnement à l'octet :

| Surface | Ce qu'on voit | Prérequis |
|---|---|---|
| **LLM-traces** (`LlmTracePanel`) | messages / tool décidé / tokens par étape | run lancé (T1 câblé) |
| **App-traces** (page Proxy) | effets d'action gouvernés (action_type, resource, réponse) | `INSPECT_IA_AGENTS_PROXY_DEBUG=on` (ON par défaut sous `all up` et Docker) |
| **Wire** (timeline décision) | octets réseau + timeline `réflexion → effet` par run, actions surlignées | overlay wire actif (`all up`) + route Wire sélectionnée |

Le bouton **Démarrer/Arrêter le réseau (wire)** de la console pilote l'overlay
(`POST /proxy/wire/overlay`). Il est deny-by-default (`INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL`)
et n'est autorisé que dans le chemin observe : lancer via `./recette.sh all up`
(ou `platform up --wire`) l'active. En dehors, un clic renvoie 403 — c'est voulu.
Il ne fonctionne que si l'API tourne bare-host (elle shelle `./recette.sh wire`).

Pour la timeline « à quel moment une action non désirée arrive » : filtrer la
page wire sur le `run_id`, la section **Timeline décision** ordonne les étapes et
surligne les actions (tool décidé / appel mutant).

## 5. Rappel des limites (honnêteté d'étude)

- Le mock ne produit pas de raisonnement — seulement des décisions scriptées.
- La capture LLM voit les appels qui passent par la boucle `lane_b` ; un appel
  hors plateforme n'est pas capturé.
- La capture wire ne voit que le trafic **routé par le proxy** ; sous Docker,
  router le trafic par l'overlay demande en plus `INSPECT_IA_AGENTS_WIRE_PROXY`
  + une topologie réseau adaptée (voir `docker-compose.yml`, service `wire-proxy`).
