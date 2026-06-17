# Recette de detection de surface -- la sonde discovery VOIT-elle l'agent ?

> La recette qui prouve la these : **si l'outil ne voit pas les agents, c'est
> un echec**. Elle evalue, surface d'observation par surface d'observation, si un
> outil de discovery (la sonde discovery) detecte un agent simule. Un agent detecte sur
> AUCUNE surface fait passer la scorecard au ROUGE. Conception fondatrice :
> `docs/plans/2026-06-16-discovery-probe-recette-host-docker-design.md`.
> Plan d'implementation : `docs/plans/2026-06-16-discovery-probe-surface-detection.md`.

## Les quatre surfaces

La sonde discovery observe un agent a travers plusieurs surfaces d'interception (RFC AgentRail) :

- `hook_subprocess`, `hook_mcp`, `hook_sdk` -- la famille **hook** inline : un shim
  dans le processus de l'agent voit le tool-call structure (la vue `ProxyTrace` du
  banc d'essai).
- `ebpf_wire` -- la famille **eBPF/syscall** : une sonde noyau voit le flux reseau
  brut (la vue `WireFlow` du banc d'essai), meme au travers de la frontiere Docker (un seul noyau).

## Les deux vues que le banc d'essai possede deja

Un run simule produit deux vues deterministes, reutilisees telles quelles :

- `proxy_traces` (`recette/platform/proxy/tracing.py::ProxyTrace`) -> la vue hook.
- `wire_flows` (`recette/platform/proxy/wire.py::WireFlow`) -> la vue eBPF/wire.

`recette/surface/surfaces.py::project_surfaces` projette un run sur chaque surface
(pur, trie, I4).

## Le ghost, pierre angulaire

`corpus/surface/ghost-direct-db` est un agent dont l'egress natif contourne le
SDK : il produit un `wire_flow` mais AUCUN `proxy_trace`. Il est donc **invisible
sur les surfaces hook** et **capture uniquement sur la surface wire/eBPF**. C'est
pour cela que la couverture par surface est importante : un detecteur uniquement
hook le manquerait. Meme dualite wire-vs-audit que
`recette/platform/proxy/reconcile.py::reconcile_run`.

## Le lancer

```
python -m recette surface
```

Affiche la scorecard de detection (JSON) et sort avec le code 0 si et seulement si
chaque agent est detecte sur au moins une surface. Exemple de sortie (2 sujets) :

```
{
  "detected_per_surface": {"ebpf_wire": 2, "hook_mcp": 1, "hook_sdk": 1, "hook_subprocess": 1},
  "false_negatives": [],
  "ok": true,
  "total_agents": 2
}
```

`ebpf_wire` detecte les deux ; les surfaces hook ne detectent que le PR bot
conforme (1/2) -- le ghost est l'angle mort des hooks. `false_negatives` liste tout
agent vu nulle part (l'echec de la these) ; une liste non vide sort avec le code 1.

Ce gate tourne a l'interieur de `make recette` (c'est une dependance de la cible
`recette`) : un agent simule que la sonde discovery ne verrait sur AUCUNE surface fait passer
toute la recette au ROUGE, en CI, automatiquement -- jamais quelque chose a
attraper a la main.

## Le gate rouge -- le sujet negatif `vanished`

`corpus/surface/_negative/vanished` est un sujet NEGATIF committe : un agent
qui n'a rien produit d'observable (`proxy_traces` vide ET `wire_flows` vide),
il n'est donc detecte sur AUCUNE surface. Son ground-truth est `detected_anywhere: false`.

Il vit sous `_negative/` pour que le run vert `recette surface` ne l'evalue PAS
(le loader `load_surface_subjects` ignore les repertoires prefixes par `_`). Il est
charge separement par `load_surface_negatives()` et exerce par
`tests/test_surface_negative.py`, qui assert que la scorecard passe au ROUGE sur lui
(`ok == false`, `false_negatives == ("vanished",)`). Cela prouve que le gate de la
these se declenche depuis un sujet de corpus committe, pas seulement depuis un
literal de test unitaire.

## Brancher la vraie sonde discovery

L'oracle de reference (`ReferenceSurfaceDiscoveryAdapter`) est le gabarit. Une vraie
sonde discovery se branche en implementant le protocol `SurfaceDiscoveryAdapter`
(`recette/surface/detect.py`) -- a partir d'une `SurfaceObservation`, renvoyer un
`DiscoveryResult`.

`recette/surface/http_adapter.py::HttpSurfaceDiscoveryAdapter` est l'implementation
HTTP prete a l'emploi (calquee sur `recette/http_adapter.py`) : elle envoie en POST
chaque observation (`{surface, visible}`) vers la route de detection de la sonde discovery
(`/v1/detect`, SUPPOSEE en attendant l'API de la sonde discovery), deballe une enveloppe
`{success, data}`, et renvoie un `DiscoveryResult`. Config (R5/R8) : URL de base
depuis `INSPECT_IA_AGENTS_PROBE_URL` (defaut `http://127.0.0.1:8085`), bearer
token depuis `INSPECT_IA_AGENTS_PROBE_TOKEN`, tenant depuis
`INSPECT_IA_AGENTS_TENANT`. httpx est importe paresseusement avec un fallback
stdlib sans dependance, de sorte que le package n'a besoin d'aucun reseau pour
s'importer.

## Gates

```
.venv/bin/python -m unittest discover -s tests
make recette        # includes the `surface` detection gate
.venv-pyaudit/bin/ruff check recette/ tests/ && .venv-pyaudit/bin/mypy recette/
```

## Voir aussi

- `.claude/rules/determinism-replay.md` (I4) -- projection/detection/scorecard pure + testee en replay.
- `docs/runbooks/private-dns.md` -- les serveurs du lab vers lesquels les comms simulees sont routees.
- `recette/adapters.py` -- la famille `DiscoveryAdapter` / `IdentificationAdapter` que ceci etend.
