# Plan : APEX -- Fondation corpus de recette agents GitHub/GitLab
Date : 2026-06-11
Status : TERMINE
Session : apex-20260611-recette-corpus
Invariants concernes : I3 (identite), I4 (determinisme/replay), I5 (proxy/forge mediation)

## Objectif
Livrer la fondation Python de la recette : agents de test deterministes (manifest + scenario)
qui agissent sur une forge GitHub/GitLab, un lab en memoire (zero-dep), un harnais qui invoque
discovery + identification via adaptateurs pluggables et compare au ground-truth (scorecard).

## Decision THINK (alternative retenue)
- ALT A (rejetee) : mock HTTP FastAPI + PyGithub/python-gitlab. Deps absentes, non deterministe, speculatif.
- ALT B (RETENUE) : GitForge en memoire. LabForge (defaut, zero-dep, deterministe, action log) +
  RealForge (optionnel, SDK garde-fou). Adaptateurs discovery/identification pluggables lisant l'action log.

## Etapes
- [x] S1 events.py : AgentAction dataclass (mappe AgentActionEvent) + horloge logique deterministe (I4)
- [x] S2 forge.py : GitForge protocol + LabForge (in-memory) + RealForge (optionnel, import garde-fou) (I5)
- [x] S3 manifest.py + scenario schema : load + validation jsonschema (manifest, ground-truth, scenario)
- [x] S4 agent.py : TestAgent rejoue un scenario -> action log deterministe
- [x] S5 adapters.py : Discovery/Identification protocols + ReferenceAdapter (calcule 4 dimensions)
- [x] S6 scorecard.py + harness.py : itere corpus, compare ground-truth, scorecard (detection rate, accuracy/dimension, FP/FN)
- [x] S7 __main__.py : python -m recette validate | run
- [x] S8 corpus : 2 corrects (gh,gl) + 4 violation_type x (github, gitlab) = 10 agents
- [x] S9 tests/ unittest : 12 tests verts (determinisme, schemas, couverture, orthogonalite, bad-tool FN)
- [x] S10 pyproject.toml (extras real/dev) + maj recette-corpus.md (code Python exempte rust-conventions)

## Ecarts et replanification
- REPLAN S5/S8 : 1er run, le reference adapter contredisait le ground-truth de gl-readonly-overreach
  sur policy+behavior. Decision : dimensions ORTHOGONALES (1 violation_type = 1 dimension cassee).
  Ground-truth corrige -> recette 100%. Trace dans decision_log.jsonl.

## Resultat
10 agents (2 corrects + 8 incorrects couvrant 4 violation_type x 2 plateformes). Reference adapter
matche le ground-truth a 100% sur les 4 dimensions. Test negatif : un outil "always-correct"
produit bien 8 faux negatifs detectes par le scorecard. Recette : py_compile OK, 10 valides,
12 tests verts, run exit 0. ruff non installe -> N/A (non reclame).

## Recette (adaptee Python, pas Rust/React)
- STATIC : python3 -m py_compile sur tous les .py ; validation jsonschema de tout le corpus
- RUNTIME : python3 -m unittest -> tout vert ; python -m recette run -> scorecard 100% vs ground-truth (reference adapter)
- REGRESSION : pas de baseline anterieure (premier cycle)

## Decisions prises
- Zero dependance dure : seul jsonschema (present). SDK reel = extra optionnel.
- Determinisme : event_id = seq, timestamp = horloge logique injectee (pas de now()/random) (I4).
- Lab = forge en memoire (pas FastAPI).

## Resultat
(a remplir en COMPLETE)
