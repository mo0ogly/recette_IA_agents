# Plan : Orchestration styles (sequential/concurrent) + Corpus browser
Date : 2026-06-13
Status : TERMINE
Invariants concernes : I3 (identity), I4 (deterministic replay), I6 (approval gate)

## Objectif
1. Extend the multi-agent orchestration recette beyond handoff to the two other
   real MAF orchestration styles: sequential and concurrent. Grounded on the
   real microsoft/agent-framework builders (SequentialBuilder: ordered chain,
   each participant once in order; ConcurrentBuilder: fan-out/fan-in, each once
   on the same input). Closes the "concurrent/sequential orchestration kinds"
   part of the Multi-agent TODO.
2. Frontend: a Corpus browser page consuming the existing GET /subjects (which
   has no UI today), listing every subject across families (git_agent / maf_agent
   / maf_orchestration) with family, violation_type and expected verdict. React +
   Vite, reuse existing styles -- no new CSS/HTML files.

## Real MAF model reused
- SequentialBuilder: "participants run in order, sharing a conversation"; each
  runs exactly once; last is terminator.
- ConcurrentBuilder: dispatcher fans out the same input to all participants;
  each runs once; aggregator emits in deterministic participant order.

## Mapping to recette (judged unit = team, by style)
- `team.style` discriminator: handoff (existing) | sequential | concurrent (default handoff).
- handoff: unchanged (hops + declared edges + start_agent + termination/loop).
- sequential: behavior = run order equals the declared participant order, each once;
  capabilities = every executed participant is declared.
- concurrent: behavior = each declared participant executed exactly once (set match, no duplicate);
  capabilities = every executed participant is declared.
- identity (I3) and policy (I6): per-participant tool checks, shared across styles.
- Returns the existing IdentificationResult -> same ground-truth comparison.

## Etapes
- [x] Schema: add `style` to maf-orchestration; add `order` to the run, make `hops` optional
- [x] `recette/maf_orchestration.py`: style-aware judge (sequential/concurrent branches), pure (I4)
- [x] Corpus: sequential (1 correct + 1 negative), concurrent (1 correct + 1 negative), mono-axis
- [x] Tests: extend tests/test_maf_orchestration.py (per-style dims, orthogonality, determinism)
- [x] Frontend: `console/src/pages/corpus/` browser of GET /subjects (fixture + render-assert), nav + route
- [x] Gates: recette report PASS, full backend + console suites green, ruff/mypy/bandit + tsc clean

## Resultat
Done. orchestration 9/9 teams PASS (5 handoff + 2 sequential + 2 concurrent),
aggregate report PASS. 700 backend tests + 206 console tests green; ruff/mypy/
bandit clean; tsc 0 errors. judge stays a pure fn of (team, run) -> replays
identically (I4). New Corpus console page lists all 24 subjects across the three
families from the previously-unconsumed GET /subjects, filterable by family,
reusing discovery table styling (no new CSS). Concurrent behavior counts each
declared participant once so an undeclared fan-out member is a capabilities-only
break (keeps negatives mono-axis).
