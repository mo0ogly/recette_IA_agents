# RETEX APEX -- G2 durable approval (I6)

Date : 2026-06-13
Branch : feat/g2-durable-approval
Agentic score : 44/50

| Criterion | Score | Comment |
|-----------|-------|---------|
| C1 Decomposition | 8/10 | 3 sous-taches (preuve, doc+correction, recette) -- petit cycle car gap surdimensionne |
| C2 Planning (THINK) | 10/10 | OBSERVE a INVALIDE la premisse du gap (R18) ; 2 alternatives (Temporal rejete car stub, vs prouver l'existant) |
| C3 Replanning | 8/10 | 0 REPLAN code ; le vrai "replan" fut de REQUALIFIER le scope apres verification |
| C4 Tooling | 9/10 | .venv (tests) + .venv-pyaudit (gates), mmdc valide mermaid |
| C5 Traceability | 9/10 | PLAN + RETEX + runbook + TODO corrige + commit branche |

Sous-taches : 3 SUCCESS / 0 PARTIAL / 0 FAILURE / 0 REPLAN

## Le fait marquant : un gap surdimensionne, corrige par verification (R18)

Le TODO G2 affirmait "durabilite non cablee, escalate ne survit pas au restart". En LISANT
le code (pas le docstring "PLACEHOLDER"), l'approbation est DEJA event-sourcee et durable :
inbox = fold sur le log append-only (I1), `resolve_approval` anti double-resolution + append,
`sweep_timeouts` -> TIMEOUT jamais approve. Plutot que fabriquer un Temporal inutile (et
intestable sans serveur -> stub interdit), la vague a PROUVE l'existant et corrige la premisse.

## Livre

- `tests/test_approval_durability.py` (4 tests) : durabilite RESTART contre un
  `SqliteEventStore` PERSISTE -- pending survit, resolution survit, double-resolve post-restart
  refuse (InvalidTransition), timeout post-restart -> TIMEOUT, jamais execute. C'etait la seule
  preuve manquante (les tests existants utilisaient un store in-memory intra-process).
- `docs/runbooks/approval-durability.md` + 2 mermaid (lifecycle stateDiagram, sequence restart).
- TODO platform-gaps G2 corrige (R18) : durabilite OK ; residuel reel documente.

## Preuves (faits)

- 4 tests durabilite verts ; suite complete 724 OK (9 skip).
- gates : ruff + bandit 0 sur le delta ; mypy delta N/A (test hors package `recette`).
- mermaid valides via mmdc.

## Residuel honnete

Pas de TIMER autonome : `POST /approvals/sweep-timeouts` doit etre declenche par un scheduler
externe (cron/systemd/k8s). Temporal le ferait nativement -- non fait faute de serveur (un
stub serait interdit). Ticket de suite dans le TODO.

## R28 flag-not-sweep

`recette/run_view.py` (untracked, autre session, importe `recette.viz` inexistant) provoque 1
erreur mypy hors de mon scope -- FLAGGEE, ni corrigee, ni commitee, ni revertee.

## Evolutions

- Quick win : un systemd timer / CronJob exemple pour le sweep (5 min).
- Notable : un endpoint/worker interne qui auto-declenche le sweep a intervalle (sans cron).
- Refactor : adopter Temporal pour le timer durable (decision a tracer, cf G7).
