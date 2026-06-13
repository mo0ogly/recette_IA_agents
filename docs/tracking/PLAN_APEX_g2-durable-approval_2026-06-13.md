# Plan : G2 -- Approbation durable (I6)

Date : 2026-06-13
Status : TERMINE
Branch : feat/g2-durable-approval (depuis main)
Invariants : I6 (blocage sur approbation), I1 (resolution = nouvel evenement), I4 (now capture)

## Constat (verifie, corrige R18)

Le TODO G2 affirmait "durabilite non cablee, escalate ne survit pas au restart" -- en se
fiant au docstring "PLACEHOLDER for a Temporal durable workflow". VERIFICATION du code :
le systeme est DEJA event-source et durable :
- `gateway.submit` : escalate -> append ACTION_REQUESTED (pending), aucune execution (I6).
- `gateway.resolve_approval` : anti double-resolution (InvalidTransition), append
  APPROVAL_RESOLVED (I1, nouvel evenement, jamais mutation).
- `gateway.sweep_timeouts` : resout les expires en TIMEOUT, jamais approve.
- `ApprovalService.pending()` : fold sur le log append-only -> reconstruit a tout moment.
Tests existants : escalate-bloque, denied-jamais-execute, double-resolution-rejetee,
timeout-jamais-approuve, sweep-jamais-execute.

MANQUE (le vrai delta) : aucune preuve que l'inbox survit a un RESTART de process contre un
store SQLite PERSISTE (les tests existants utilisent InMemoryEventStore intra-process).
RESIDUEL reel : le TIMER d'auto-timeout n'existe pas -- le sweep doit etre declenche de
l'exterieur (scheduler/cron). Temporal le ferait nativement. Pas de Temporal ici (pas de
serveur -> un stub serait interdit).

## Decision

Alternative A (vrai Temporal) REJETEE : pas de serveur -> stub intestable (NO STUB), et la
durabilite est deja satisfaite par l'event-sourcing. Alternative B RETENUE : prouver la
durabilite restart contre SQLite, corriger la premisse fausse du TODO, documenter le cycle +
le seul residuel (auto-timer = scheduler externe).

## Etapes

- [ ] S1 tests/test_approval_durability.py : restart contre SqliteEventStore persiste --
      pending survit, resolution survit, double-resolution post-restart rejetee, timeout
      post-restart -> TIMEOUT (jamais approve), executed=False. Generateur d'id restart-safe.
- [ ] S2 doc : runbook docs/runbooks/approval-durability.md + mermaid (lifecycle event-source
      + fold au restart + note scheduler) ; corriger l'entree G2 du TODO platform-gaps (R18).
- [ ] S3 RECETTE : suite complete verte + gates ruff/mypy/bandit clean sur le delta.

## Done

- Test restart : kill simule (nouveau store sur le meme fichier) -> pending/resolution
  reconstruits ; double-resolution post-restart -> InvalidTransition ; timeout -> TIMEOUT.
- TODO G2 corrige (durabilite OK, residuel = scheduler). Suite verte, gates clean.

## Ecarts / replan

(a remplir)
