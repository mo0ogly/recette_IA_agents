# Runbook -- API de recette Track U (U1)

L'API U1 (`recette/api/`) expose chaque capacite de la CLI -- runs identification /
discovery / Lane B, config, catalogue -- via HTTP, plus un flux d'evenements live en
WebSocket. Elle reutilise directement le package `recette` (aucune logique metier
dupliquee) et le package coeur `recette` n'importe jamais `recette.api` -- FastAPI est
un extra optionnel.

## Installation

```bash
pip install -e '.[api]'
```

(ou utiliser le `.venv` du projet, qui a deja l'extra `[api]` installe).

## Lancement

```bash
make api
# or
python -m recette.api
```

Hote/port via env (valeurs par defaut `127.0.0.1:8090`) :

| Variable d'env | Defaut |
|---------|---------|
| `INSPECT_IA_AGENTS_API_HOST` | `127.0.0.1` |
| `INSPECT_IA_AGENTS_API_PORT` | `8090` |

## Endpoints

| Methode | Chemin | Role |
|--------|------|---------|
| GET | `/health` | liveness |
| GET | `/agents` | catalogue (corpus d'identification, surfaces de discovery, agents lane_b enregistres) |
| POST | `/agents/register` | enregistre un agent Lane B dans la config |
| GET/POST/PUT/DELETE | `/config/agents[/{id}]` | CRUD de la config des agents Lane B |
| GET/POST/DELETE | `/config/ai-backends[/{id}]` | CRUD de la config des backends IA (aucun secret stocke) |
| POST | `/runs` | lance un run `{kind: identification\|discovery\|lane_b, params}` |
| GET | `/runs/{id}` | statut du run |
| GET | `/runs/{id}/events` | trames d'evenements bufferisees (repli par polling) |
| POST | `/runs/{id}/stop` | demande un arret cooperatif |
| WS | `/runs/{id}/ws` | flux de trames d'evenements live (transport WebSocket) |

## Utilisation du WebSocket

Se connecter a `ws://host:port/runs/{id}/ws`. Le serveur pousse des trames JSON de la
forme `{seq, type, data}`. Le flux se termine par une trame terminale :

```json
{"type": "end", "data": {"status": "..."}}
```

## Exemple de run Lane B

Deterministe / hors ligne (fournir un `stub_script`) :

```json
POST /runs
{"kind": "lane_b", "params": {"agent_id": "a1", "stub_script": [...]}}
```

Sans `stub_script`, l'`ai_backend_id` de l'agent se resout vers un provider live
(cle du provider fournie via env -- R8).

## Garde-fou du mode reel

Le lab est la forge par defaut (aucun effet de bord). La forge en mode reel n'est
**pas** activee en U1 tant qu'une tache future ne cable pas `params.real` plus
`INSPECT_IA_AGENTS_REAL_ALLOWLIST` (env).

Les secrets (cles de provider, tokens) ne sont jamais stockes dans la config --
toujours via env (R8).

## Note de suivi

L'API suppose un lab mono-utilisateur ; l'authentification est un suivi ulterieur du
Track U.
