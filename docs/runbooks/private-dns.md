# Resolveur DNS prive -- runbook

> Les serveurs du lab portent des noms internes stables (`fqdn` + `aliases`) au
> lieu de `127.0.0.1:port` brut. Le proxy resout un nom vers une entree de serveur
> de maniere deterministe (I4), l'enregistre comme `ProxyTrace.target` (realisme de
> la trace) et -- quand le **containment** global est actif -- refuse tout nom non
> declare avec un evenement audite `resolution_denied` et SANS appel reseau
> (fail-safe, un signal d'exfiltration).
>
> Conception : `docs/plans/2026-06-15-private-dns-resolver-design.md`.
> Code : `recette/platform/netname/resolver.py` (pur), gate du proxy dans
> `recette/api/runners.py`, config dans `recette/api/config_store.py`.

## Le modele de noms

Chaque entree de serveur dans `config/inspect_ia_agents.config.json` peut declarer :

- `fqdn` -- nom interne canonique (par ex. `api.github.com`). Optionnel et
  retrocompatible : un serveur sans `fqdn` se resout toujours par son `id`.
- `aliases` -- noms alternatifs qui se resolvent vers le meme serveur.

Un nom se resout par `fqdn` -> `alias` -> `id`, dans cet ordre. La resolution est une
fonction pure de `(name, servers, containment)` -- pas de socket, pas d'horloge, pas
d'aleatoire -- donc elle est stable au replay (I4) et n'entre jamais dans `decide()`.

## Containment (la gate d'allowlist)

Un unique drapeau global `containment` (au niveau racine de la config) bascule le comportement :

- **off (par defaut)** -- realisme uniquement : un nom inconnu retombe sur le chemin
  `id` legacy. Rien n'est refuse.
- **on** -- le resolveur est une allowlist : un nom non declare leve
  `ResolutionDenied`, le proxy emet un evenement audite `resolution_denied` et
  n'effectue AUCUN appel (deny-by-default fail-safe ; defense en profondeur par-dessus
  la mediation par proxy, jamais un remplacement de celle-ci).

## Pilotage depuis la console

Page Serveurs (`/servers`) :

- **Onglet Config** -- chaque formulaire de serveur dispose des champs
  `FQDN (private DNS, optional)` et `Aliases (comma-separated)`, plus un bascule
  global **Private-DNS containment** (lit/ecrit `GET/PUT /config/containment`).
- **Panneau de test** (`ServerTestPanel`) -- une sonde **Resolve name** appelle
  `POST /config/resolve` et affiche soit l'endpoint resolu
  (`name -> server_id (fqdn)`), soit un badge `denied` avec la raison. Une sonde
  refusee est un diagnostic reussi (HTTP 200, `resolved: false`), pas une erreur,
  et n'ajoute aucun evenement.

## API

| Verbe | Route | Corps | Retourne |
|------|-------|------|---------|
| GET  | `/config/containment` | -- | `{"containment": bool}` |
| PUT  | `/config/containment` | `{"enabled": bool}` | `{"containment": bool}` |
| POST | `/config/resolve` | `{"name": str, "containment"?: bool}` | dict resolved / denied |

Resultats de `/config/resolve` (dict brut, pas d'enveloppe) :

```
resolved : {"name": "api.github.com", "resolved": true, "server_id": "gh-mock", "fqdn": "api.github.com"}
denied   : {"name": "evil.example.com", "resolved": false, "reason": "not_in_allowlist"}
legacy   : {"name": "<unknown>", "resolved": false, "reason": "unknown_legacy"}   # containment off
```

## Preuve live (R14)

Avec la plateforme demarree (`./recette.sh platform up`, API sur `:8090`) :

```
curl -s -X POST http://localhost:8090/config/resolve -H 'content-type: application/json' -d '{"name":"api.github.com","containment":true}'
curl -s -X POST http://localhost:8090/config/resolve -H 'content-type: application/json' -d '{"name":"github.lab.internal","containment":true}'
curl -s -X POST http://localhost:8090/config/resolve -H 'content-type: application/json' -d '{"name":"evil.example.com","containment":true}'
```

Observe (2026-06-15) : `api.github.com` et l'alias `github.lab.internal` se
resolvent tous deux vers `gh-mock` ; `evil.example.com` retourne `resolved: false`,
`reason: not_in_allowlist` -- refuse, aucun appel.

## Gates

```
.venv/bin/python -m unittest discover -s tests
make recette
./recette.sh console-test
./recette.sh console-build
```

## Liens connexes

- `.claude/rules/determinism-replay.md` (I4) -- le resolveur est pur + teste au replay.
- `.claude/rules/frontend-contract-gate.md` (R16) -- fixtures de la console capturees en live.
- `docs/runbooks/lab-realistic-doubles.md` -- le lab double les noms vises.
