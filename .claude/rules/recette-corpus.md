# Recette Corpus -- conventions des agents de test GitHub/GitLab

Ce repo produit un CORPUS d'agents de test (sujets ground-truth) qui valide deux outils :
**discovery** (doit reperer l'agent) et **identification/evaluation** (doit juger s'il est correct).

## Cible d'execution

- **Lab simule par defaut** : endpoints GitHub/GitLab mockes, zero effet de bord reel, zero
  token reel, reproductible (coherent avec I5 proxy + I4 replay).
- **Reel en option** : orgs/repos de test dedies + vrais tokens, pour validation finale.
  Jamais d'effet de bord sur un repo de prod. Secrets via env (voir `no-hardcoded-secrets.md`).
- Le mode est porte par le manifest (`runtime.lab_mode` / `runtime.real_mode`).

## Les 4 dimensions de "correct" (l'identification juge les 4)

1. **Identite (I3)** : l'agent est bien celui qu'il pretend etre (auth_method, principal).
2. **Capabilities declarees vs reelles** : les actions effectuees restent dans `capability_scope`.
3. **Conformite policy** : les actions respectent allow/deny/escalate attendus pour ce type d'agent.
4. **Comportement attendu** : l'agent fait ce que son role prevoit (un PR-bot ouvre des PR pertinentes, pas du spam).

Le `ground-truth.json` d'un agent renseigne l'attendu sur CHACUNE des 4 dimensions + le verdict global.

## Corpus = positifs ET negatifs (OBLIGATOIRE)

Sans cas negatifs on ne valide pas que l'identification sait dire "non". Pour chaque agent
INCORRECT, `violation_type` indique l'axe casse :
- `identity_mismatch` (I3 casse)
- `capability_overreach` (declare read-only, ecrit)
- `policy_violation` (fait une action deny/escalate sans approbation)
- `behavior_anomaly` (spam, action hors role)

Cible de couverture : au moins 1 agent correct et 1 agent incorrect par `violation_type`,
sur GitHub ET GitLab.

## Langage d'implementation (recette = Python)

Le code de la recette (agents de test, lab/forge, harnais, adaptateurs) est en **Python**
dans le package `recette/`. Il est EXEMPTE des `rust-conventions.md` (qui visent la plateforme
Rust/Axum). Determinisme (I4) impose neanmoins : pas de `time.time()`/`datetime.now()`/`random`
dans l'execution d'un agent -- horloge logique injectee (`recette.events.LogicalClock`),
`event_id` derive d'une sequence. Zero dependance dure hors `jsonschema` ; SDK reels
(`PyGithub`, `python-gitlab`) = extra optionnel `[real]`.

## Structure

```
corpus/
  README.md
  schemas/
    agent-manifest.schema.json     # ce que l'agent DECLARE (identite + capability_scope)
    scenario.schema.json           # ce que l'agent FAIT reellement (actions deterministes ordonnees)
    ground-truth.schema.json       # ce que la recette ATTEND des outils (discovery + 4 dimensions + verdict)
  agents/
    correct/<slug>/{manifest.json, scenario.json, ground-truth.json}
    incorrect/<slug>/{manifest.json, scenario.json, ground-truth.json}
recette/                           # package Python (forge, agent, adapters, harness, scorecard)
tests/                             # unittest stdlib (zero install)
```

Chaque agent de test :
1. DECLARE son identite + capabilities dans `manifest.json` (valide contre `agent-manifest.schema.json`).
2. SCRIPTE ses actions reelles dans `scenario.json` (valide contre `scenario.schema.json`).
   L'ecart manifest (declare) vs scenario (reel) est ce qui rend l'agent correct ou incorrect.
3. PORTE son ground-truth dans `ground-truth.json` (valide contre `ground-truth.schema.json`).

## Orthogonalite des dimensions (REGLE)

Un agent INCORRECT casse EXACTEMENT UNE des 4 dimensions (le `violation_type` correspondant) ;
les 3 autres restent conformes. Cela rend l'accuracy par dimension mesurable et chaque cas
negatif mono-axe. Un test (`test_each_negative_breaks_exactly_one_dimension`) le verifie.

## Deux recettes : identification (action-log) et discovery (repos)

- **Identification** (`corpus/agents/`) : agents = action-logs deterministes (manifest +
  scenario), juges sur 4 dimensions. CLI : `python -m recette run`.
- **Discovery** (`corpus/repos/`) : agents = vrais repos GitHub publiables (code + CI/CD +
  manifest `.agentrail`) que le GitHubScanner du collegue scanne. Ground-truth = proprietes
  INVARIANTES (detection, count/dedup, couverture action_pattern, target, ordre relatif de
  risque, determinisme I7, presence de policy) -- jamais les valeurs opaques
  (`canonical_agent_id`, score exact). CLI : `python -m recette discovery --adapter reference|http`.
  Publication des repos : `python -m recette publish <slug> --owner <org> [--apply]`
  (dry-run par defaut). Detail : `docs/runbooks/github-discovery-recette.md`.

## Invocation

```
python3 -m recette validate                      # schema-valide agents + repos discovery
python3 -m recette run                           # identification -> scorecard 4 dimensions
python3 -m recette discovery --adapter reference # discovery -> scorecard invariants (offline oracle)
python3 -m recette publish <slug> --owner <org>  # publie un repo de test (dry-run)
python3 -m unittest discover -s tests
```

Les outils reels discovery/identification se branchent en implementant les protocols
`DiscoveryAdapter` / `IdentificationAdapter` (`recette/adapters.py`). Les `Reference*Adapter`
fournis sont un evaluateur correct de reference (et le gabarit de ce qu'un vrai outil doit produire).

## Boucle de recette (mesurable)

```
pour chaque agent du corpus :
  lancer discovery        -> detecte ? compare a expected_discovery.detectable
  lancer identification   -> verdict + 4 dimensions ? compare a ground-truth
  PASS si tout matche le ground-truth, FAIL sinon, tracer la preuve
agreger : detection rate, accuracy par dimension, faux positifs / faux negatifs
```

L'interface d'invocation des outils discovery/identification (CLI vs HTTP) est branchee via
un adaptateur dans le harnais -- a definir quand l'interface des outils est connue.

## Mapping AgentActionEvent

Les actions des agents mappent sur le modele canonique : `target_system = github|gitlab`,
`action_type = read_repo|list_repos|open_issue|comment_issue|open_pr|merge_pr|push|manage_webhook`.
Voir `canonical-event-model.md`.
