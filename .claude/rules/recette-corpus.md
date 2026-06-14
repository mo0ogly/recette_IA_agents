# Recette Corpus -- conventions des agents de test GitHub/GitLab

Ce repo produit un CORPUS d'agents de test (sujets ground-truth) qui valide deux outils :
**discovery** (doit reperer l'agent) et **identification/evaluation** (doit juger s'il est correct).

## L'objet du repo (a lire en premier)

L'objet de ce repo n'est PAS d'exploiter des agents en production : c'est de fournir un
**corpus ground-truth** servant de banc d'essai a deux outils EXTERNES que des collegues
developpent. Le repo est l'etalon ("voici la verite, ton outil tombe-t-il dessus ?").

Un meme "agent" porte TROIS formes selon la recette qui le consomme. Ne pas les confondre :

| Forme | Ou | Ce que c'est | Outil externe qui le consomme |
|-------|----|--------------|-------------------------------|
| **Agent runtime** | `config/inspect_ia_agents.config.json` (bouton "Lancer" du dashboard, run Lane B) | un agent qui AGIT en direct contre le lab et produit un action-log | aucun direct -- son log alimente l'**identification** |
| **Sujet d'identification** | `corpus/agents/<slug>/` (`manifest` + `scenario` + `ground-truth`) | un action-log FIGE + sa verite sur les 4 dimensions | outil d'**identification** (juge correct/incorrect) |
| **Sujet de discovery** | `corpus/repos/<slug>/repo/` (+ `.inspect_ia_agents`) | un VRAI repo publiable (code + manifest) analyse statiquement | outil de **discovery** (scanner de sources) |

Consequences a garder en tete :

- **La discovery ne voit JAMAIS le runtime.** Le scanner externe lit la SOURCE (arbre repo +
  `.inspect_ia_agents`), il n'observe pas un agent qui tourne. Le trafic HTTP vers le lab (port 8082)
  est invisible pour la discovery. Pour qu'un outil de discovery "voie" un agent, il faut le
  publier comme repo (`python -m recette publish <slug> --owner <org>`), pas le lancer.
- **L'identification ne voit JAMAIS la source.** Elle juge un action-log (ce que l'agent A FAIT),
  pas le code du repo.
- **Le dashboard = cockpit operateur** : il lance un agent runtime et montre ses actions
  (start/step/result/end). C'est de l'identification (production d'action-log), jamais de la discovery.
- L'ecart **declare (manifest) vs reel (scenario / action-log)** est ce qui rend un agent
  correct ou incorrect -- c'est le coeur juge par l'identification.

## Carte de lecture -- comprendre un agent et son fonctionnement (Claude lit CECI)

Pour comprendre ce qu'est un agent, ce qu'il declare, comment il s'execute et
comment il est juge, lire dans CET ordre (chemins verifies) :

1. **Ce qu'un agent declare** :
   - `corpus/schemas/agent-manifest.schema.json` -- schema unifie (discriminant `kind`).
   - `config/inspect_ia_agents.config.json` -- les agents runtime du dashboard (champs
     `ai_mode`, `ai_backend_id`, `capability_scope`, `target_system`, `server`, `scenario`).
2. **Comment un agent s'execute (boucle decide -> act)** :
   - `recette/lane_b.py` -- la boucle: `build_tools(capability_scope)` expose les
     outils, l'LLM decide, `execute_tool` agit. Outils = le `capability_scope`.
   - `recette/tools.py` -- catalogue d'outils + execution.
   - `recette/llm.py` -- les 11 providers (mock `StubLlm`/`ReplayLlm` + reels:
     groq, anthropic, openai, gemini, mistral, deepseek, xai, openrouter, together,
     fireworks, openai_compat). Format wire tool-calls structure.
   - `recette/api/runners.py` -- branche agent+LLM+forge (`make_lane_b_runner`),
     resout le proxy par `server` (mock in-memory `LabForge` vs HTTP `ProxyForge`).
3. **Ou partent les effets de bord (I5)** :
   - `recette/platform/proxy/lab_proxy.py` -- POST `/{target_system}/execute`.
   - `recette/lab/mock_server.py` + `recette/lab/domains/*` -- le lab :8082 qui
     simule les 11 systemes (okta, github, finance, ...).
4. **Comment un agent est juge (4 dimensions)** :
   - `recette/harness.py` (identification) ; `recette/maf_judge.py` (sujets MAF).
   - Les 4 dimensions + positifs/negatifs : sections plus bas de CE fichier.
5. **Cote console** :
   - `console/src/pages/agents/index.tsx` -- CRUD agent + lancement Lane B.
   - `console/src/pages/ai-backends/index.tsx` -- onglet IA (gestion des backends).
   - `console/src/pages/dashboard/index.tsx` -- cockpit (lancer + voyant + journal).
6. **Vue d'ensemble / runbooks** :
   - `docs/ARCHITECTURE.md` (mock vs IA reelle, replay) ;
     `docs/runbooks/platform.md` et `docs/runbooks/api.md` (endpoints, run lane_b).

Voir aussi la section "L'objet du repo" ci-dessus (les 3 formes d'un agent) et
`maf-standard.md` pour la famille MAF.

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
  manifest `.inspect_ia_agents`) que le GitHubScanner du collegue scanne. Ground-truth = proprietes
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
