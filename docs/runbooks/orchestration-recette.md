# Runbook -- recette d'orchestration multi-agents (de bout en bout, rejouable)

> Diagrammes (mermaid) du modele record / replay / freeze a travers les agents,
> les equipes et les campagnes : voir [`replay-model.md`](replay-model.md).

L'unite jugee est une **equipe** : un ensemble de participants avec une structure
declaree. Quatre styles d'orchestration, chacun fonde sur un builder reel
microsoft/agent-framework :

| style | builder | forme du run | conformite (axe behavior) |
|-------|---------|-----------|------------------------------|
| `handoff` | `HandoffBuilder` | `hops` | demarre sur l'agent de depart, dans la borne de terminaison, sans boucle |
| `sequential` | `SequentialBuilder` | `order` | ordre execute == ordre des participants declares, chacun une fois |
| `concurrent` | `ConcurrentBuilder` | `order` | chaque participant declare s'execute exactement une fois |
| `group_chat` | `GroupChatBuilder` | `order` | tours bornes, aucun participant ne monopolise |
| `magentic` | `MagenticBuilder` | `order` | rounds bornes, pas de blocage (meme orateur selectionne >= 3 fois de suite) |

Les quatre dimensions sont jugees par `recette.maf_orchestration.judge_orchestration`,
une fonction pure de `(team, run)` -- un input identique se rejoue en un verdict
identique (I4).

## Corpus hors-ligne (deterministe, CI)

```
python3 -m recette validate
python3 -m recette report
```

`report` evalue `corpus/maf_orchestration/{correct,incorrect}/<slug>/`
(team.json + run.json + ground-truth.json) comme l'aire `orchestration` du
verdict agrege. Chaque negatif casse exactement une dimension (son
`violation_type`).

## Live -> record -> replay -> freeze (Groq)

Un LLM en live pilote les equipes `handoff` et `group_chat` (il choisit la route
via les outils `handoff_to_<target>` / `speak_<participant>` et les propres
outils des agents). Le run est enregistre, rejoue de maniere deterministe, et juge.

```
export GROQ_API_KEY=...                                  # R8: key via env, never hardcoded
python3 scripts/run_orchestration_live_groq.py --model llama-3.3-70b-versatile
```

Pour chaque equipe il affiche `decisions=<n> verdict=<correct|incorrect>` et
verifie que le replay reproduit le run enregistre.

### Runs live peu couteux + reproductibles (cache)

```
python3 -m recette orchestrate run <team.json> --provider groq --model llama-3.3-70b-versatile --cache /tmp/llm-cache.json
```

`--cache` enveloppe le backend dans un `CachingLlm` adresse par contenu (recette/llm_cache.py) :
chaque decision est indexee par un digest de (provider:model, system, history, tools) et
stockee dans le fichier JSON. Le premier run paie les appels live ; tout run ulterieur avec
les memes inputs est servi depuis le cache sans aucun reseau (verifie : run 1 = N misses,
run 2 = N hits). Contrairement a `ReplayLlm` (replay positionnel d'un run exact unique), le
cache est indexe par input, donc il est partage entre les runs et survit a une reorganisation.

### Une seule equipe, a la main

```
python3 -m recette orchestrate run corpus/maf_orchestration/correct/support-handoff-correct/team.json --provider groq --model llama-3.3-70b-versatile --out /tmp/run.json
python3 -m recette orchestrate replay /tmp/run.json
python3 -m recette orchestrate freeze /tmp/run.json --slug live-support-handoff --category correct --out corpus/maf_orchestration/correct
```

- `run` pilote l'equipe et ecrit un `OrchestrationRecording` (l'equipe + les
  decisions LLM ordonnees + le run produit). Persistant et autonome.
- `replay` repilote l'enregistrement avec un `ReplayLlm` : il reproduit le run
  enregistre exact (une divergence est une erreur) et affiche le verdict. Deterministe.
- `freeze` transforme l'enregistrement en sujet de corpus dont le ground-truth est
  derive du juge -- le run dynamique devient un cas de recette permanent et
  deterministe. Relancer `python3 -m recette validate` ensuite.

Les topologies `sequential`/`concurrent` sont structurelles (aucun modele requis pour router) ;
elles vivent dans le corpus hors-ligne et `tests/test_orchestrate.py`.

### Visualiser une equipe ou un run

```
python3 -m recette orchestrate viz corpus/maf_orchestration/correct/support-handoff-correct/team.json
python3 -m recette orchestrate viz /tmp/run.json --run
```

`viz` affiche un Mermaid `flowchart TD` : la structure declaree de l'equipe par style
(aretes de handoff / chaine sequentielle / fan-in concurrent / aretes pointillees du manager pour
group_chat & magentic), ou, avec `--run`, le chemin reellement route (hops numerotes
ou order, plus les appels d'outils). Pur + deterministe (recette/viz.py), conventions
issues de agent-framework `_viz.py`.

## Comment cela s'integre a la recette + aux campagnes definies

- Le corpus d'orchestration fait partie de la gate de release unique
  `python3 -m recette report` (aux cotes de l'identification, des sujets MAF et de chaque
  surface de discovery).
- La page **Corpus** de la console liste chaque sujet de toutes les familles
  (`git_agent` / `maf_agent` / `maf_orchestration`) depuis `GET /subjects`.
- Le runner live s'inscrit dans la famille existante `scripts/run_*_live_groq.py` : une
  demo live non-deterministe dont la preuve deterministe est le corpus hors-ligne
  plus `tests/test_orchestrate.py` (record -> replay -> verdict identique).

## Invariants

- I3 : l'appel d'outil d'un participant doit utiliser son `provider`/`model` declare.
- I4 : le juge est pur ; les enregistrements se rejouent a l'identique.
- I6 : un outil sous controle d'approbation (`approval: always`) doit etre approuve avant usage.
