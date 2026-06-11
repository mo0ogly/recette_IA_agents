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

## Structure

```
corpus/
  README.md
  schemas/
    agent-manifest.schema.json     # ce que l'agent DECLARE (identite + capability_scope)
    ground-truth.schema.json       # ce que la recette ATTEND des outils (discovery + 4 dimensions + verdict)
  agents/
    correct/<slug>/{manifest.json, ground-truth.json}
    incorrect/<slug>/{manifest.json, ground-truth.json}
```

Chaque agent de test :
1. DECLARE son identite + capabilities dans `manifest.json` (valide contre `agent-manifest.schema.json`).
2. PORTE son ground-truth dans `ground-truth.json` (valide contre `ground-truth.schema.json`).
3. (plus tard) a une implementation qui realise reellement les actions GitHub/GitLab.

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
