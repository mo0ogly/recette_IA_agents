# Graphe d'orchestration -- runbook

> Un run d'orchestration multi-agent (equipe MAF) vu comme un **graphe dirige** :
> noeuds = participants, aretes = handoffs ponderes par le nombre de transferts.
> Le sous-systeme calcule des signaux graphes (degres entrant/sortant, volume
> d'appels d'outils, PageRank pondere) comme indicateurs d'observabilite/risque
> sur ce que l'equipe a REELLEMENT fait, et rend une visualisation Mermaid de la
> structure declaree et du chemin reellement emprunte.
>
> Code (pur, deterministe I4) :
> - `recette/orchestration_graph.py` -- graphe d'interaction + metriques (PageRank).
> - `recette/viz.py` -- rendu Mermaid (`team_mermaid`, `run_mermaid`).
> - `recette/run_view.py` -- vue pas-a-pas (timeline + verdict + diagramme).
> - `recette/maf_orchestration.py` -- modele du run + verdict 4 dimensions.

## Pourquoi ce sous-systeme existe

La recette d'orchestration juge une EQUIPE (et plus un agent isole) sur les 4
dimensions habituelles. Mais un verdict `correct`/`incorrect` ne dit pas par ou
le run a transite ni quel agent concentre le controle. Le graphe d'orchestration
rend cette structure **lisible** (principe legibility-first) : un tiers qui n'a
pas ecrit l'equipe peut voir, depuis l'UI/le CLI seuls, le maillage des
participants, le poids de chaque handoff, et quel agent porte le plus de flux.

Le mecanisme est repris de l'approche AgentMonitor (attributs de graphe sur les
echanges d'agents) ; le regresseur ML lourd "predict-before-execute" n'est
volontairement PAS repris (il ajouterait une dependance hors stdlib, R20 -- voir
le docstring de `recette/orchestration_graph.py`).

## Le modele de donnees (entrees / sorties)

Le sous-systeme se nourrit d'un sujet d'orchestration du corpus, sous
`corpus/maf_orchestration/correct/<slug>/` ou `.../incorrect/<slug>/` :

- `team.json` -- ce que l'equipe DECLARE : `agent_id`, `name`, `style`,
  `participants` (chacun avec `agent_id`, `handoffs`, `tools`, `declared_identity`),
  `start_agent`, `termination`. Valide contre le schema `maf_orchestration`
  (`recette/manifest.py`).
- `run.json` -- ce que l'equipe a REELLEMENT fait. Charge par
  `run_from_doc(doc)` (`recette/maf_orchestration.py`) en un `OrchestrationRun` :
  - `hops` : liste de `HandoffHop(seq, source, target)` -- les transferts de
    controle (champs `from`/`to` dans le document).
  - `order` : la liste ordonnee des participants executes (chaine sequentielle,
    fan-out concurrent, ou tours group_chat/magentic).
  - `actions` -> `calls` : liste de `ToolCall(seq, agent_id, provider, model,
    target, tool_kind, approved)` -- les invocations d'outils.

`interaction_graph(run)` produit le graphe :

```json
{
  "nodes": [
    {"id": "...", "in_degree": 0, "out_degree": 0, "tool_calls": 0, "pagerank": 0.0}
  ],
  "edges": [
    {"source": "...", "target": "...", "weight": 1}
  ]
}
```

- `nodes` couvre l'union triee de `run.order`, des sources/cibles des hops et des
  `agent_id` des appels d'outils.
- `in_degree` / `out_degree` sont la somme des poids des aretes entrantes/sortantes.
- `tool_calls` est le nombre d'appels d'outils par agent.
- `pagerank` est un PageRank pondere (par power iteration), arrondi a 4 decimales.

### Determinisme (I4)

Le PageRank est calcule par power iteration avec un nombre d'iterations FIXE
(`_ITERATIONS = 60`) et un damping fixe (`_DAMPING = 0.85`), sur des noeuds
**tries**, sans horloge ni aleatoire ; les noeuds sans arete sortante
(dangling) redistribuent leur masse uniformement. `interaction_graph`,
`team_mermaid`, `run_mermaid` et `build_run_view` sont des fonctions PURES de
leurs entrees -- meme entree => meme sortie byte-stable (I4).

## Le flux

```mermaid
flowchart TD
    corpus["corpus/maf_orchestration/<slug>/<br/>team.json + run.json"];
    runfromdoc["run_from_doc()<br/>-> OrchestrationRun"];
    graph["interaction_graph()<br/>noeuds + aretes ponderees + PageRank"];
    viz["viz.team_mermaid / viz.run_mermaid<br/>diagramme Mermaid"];
    view["run_view.build_run_view<br/>timeline + verdict 4 dimensions"];
    api["GET /subjects/orchestration/{agent_id}/graph"];
    cli["python -m recette orchestrate viz"];
    page["Console /graph (Graphe d'interaction)"];

    corpus --> runfromdoc;
    runfromdoc --> graph;
    runfromdoc --> viz;
    runfromdoc --> view;
    graph --> api;
    viz --> cli;
    api --> page;
```

## Points de contact concrets

### API (FastAPI, routeur `recette/api/routers/subjects.py`, prefixe `/subjects`)

| Verbe | Route | Retourne |
|------|-------|---------|
| GET | `/subjects/orchestration/{agent_id}/graph` | le graphe d'interaction : `nodes` + `edges` ponderees + metriques par noeud |
| GET | `/subjects/orchestration/{agent_id}` | la vue pas-a-pas : `steps` (timeline) + `verdict` + `dimensions` + `violations` + `mermaid` |
| GET | `/subjects` | la liste des sujets ; un sujet d'orchestration porte `family: "maf_orchestration"` |

Le handler `orchestration_graph(agent_id)` delegue a
`build_orchestration_graph(agent_id)`, qui parcourt `discover_orchestration_dirs()`,
charge et valide `run.json`, puis appelle `interaction_graph(run)`. La vue
pas-a-pas passe par `build_orchestration_view` -> `build_run_view`
(`recette/run_view.py`), qui inclut le diagramme Mermaid du chemin route
(`run_mermaid`).

Il n'y a pas de prefixe `/api` global : ces routes sont servies telles quelles
par l'API gouvernee (port canonique `8090`, lancee uniquement via `./recette.sh`,
R19).

### CLI (`python -m recette orchestrate viz`)

Le rendu Mermaid est expose en ligne de commande (`recette/cli/parser.py`,
dispatch dans `recette/__main__.py`, implementation dans
`recette/cli/orchestrate_cmds.py::_cmd_orchestrate_viz`) :

```
python -m recette orchestrate viz <team.json>
python -m recette orchestrate viz <recording.json> --run
```

- Sans `--run`, la cible est un `team.json` : `team_mermaid` dessine la
  structure DECLAREE selon le `style` (`handoff`, `sequential`, `concurrent`,
  `group_chat`, `magentic`).
- Avec `--run`, la cible est un enregistrement (`OrchestrationRecording`) :
  `run_mermaid` dessine le chemin REELLEMENT emprunte (hops numerotes par `seq`,
  appels d'outils en aretes pointillees).

Le graphe d'interaction lui-meme (degres / PageRank) est consomme via l'API et
la console ; il n'a pas de sous-commande CLI dediee.

### Console (page `/graph`, "Graphe d'interaction")

`console/src/pages/graph/index.tsx`, montee sur la route `/graph`
(`console/src/App.tsx`). La page :

1. liste les sujets via `listSubjects()` et ne garde que ceux dont
   `family === "maf_orchestration"`,
2. recupere le graphe du sujet selectionne via
   `getOrchestrationGraph(agentId)` (`console/src/api/client.ts` ->
   `GET /subjects/orchestration/{id}/graph`),
3. rend un `flowchart LR` Mermaid (aretes ponderees + noeuds isoles) et une
   table triee par `pagerank` decroissant (`agent`, `in`, `out`, `tool calls`,
   `pagerank`).

C'est une page **lecture seule, deterministe** (I4) : aucune action externe,
aucune ecriture.

## Mode de defaillance (fail-safe)

- Sujet inconnu : `build_orchestration_graph` / `build_orchestration_view`
  renvoient `None`, le handler API leve `HTTPException(status_code=404, ...)`
  (`no orchestration subject '...'`). Pas de graphe partiel ni invente.
- `team.json` / `run.json` invalide au schema : `load_validated` leve, l'erreur
  remonte -- jamais une analyse silencieuse de donnees malformees.
- Equipe vide (0 participant) : `_pagerank` retourne `{}` (garde `n == 0`),
  pas de division par zero.
- Le sous-systeme est purement observationnel : il ne declenche aucun effet de
  bord externe, donc il n'y a pas de chemin "fail-open" possible.

## Invariants tenus

- **I4 (replay deterministe)** -- coeur du sous-systeme : PageRank a iterations
  fixes sur noeuds tries, rendus Mermaid et vue pas-a-pas tous PURS de leurs
  entrees, aucune horloge / aucun aleatoire. Meme `(team, run)` => meme sortie.
- **I6 (blocage sur approbation)** -- relaye par la vue/le verdict : un outil
  `approval: "always"` invoque sans `approved == true` casse la dimension policy
  (`_check_policy` dans `recette/maf_orchestration.py`), jamais une execution
  optimiste.
- **I3 (liaison d'identite)** -- relaye par le verdict : `_check_identity`
  verifie que chaque appel d'outil utilise le `provider`/`model` declare du
  participant. Le graphe expose le flux ; le verdict adjacent porte le jugement
  d'identite.

Le sous-systeme appartient au plan Audit (verite/observabilite/replay) : il lit
le corpus et le re-presente, il ne decide ni n'execute rien.
