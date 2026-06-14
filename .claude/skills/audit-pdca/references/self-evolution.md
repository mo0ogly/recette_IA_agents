# SELF-EVOLVE Phase -- audit-pdca self-improvement (DESIGN + GUARDRAILS)

Status: design (opt-in, flag `--evolve`)
Owner rule: R18 (verify) + R26 (no fabrication) are BLOCKING here.

## Purpose

Let the skill propose corrections to its OWN scoring methodology
(`scoring-config.md`, check definitions, formulas) from a cycle's RETEX
+ decision_log, instead of relying on a human to notice a methodology
defect by hand (as happened 2026-05-16 with the benchmark_parity N/A=50
defect: caught manually, should have been a SELF-EVOLVE proposal).

This phase NEVER changes a score. It changes the RULES that compute
scores, under a gate.

## When it runs

After FINALIZE (target met) OR after a PARTIAL close, ONLY if `--evolve`
is passed. One pass per invocation. Inputs:

- the cycle scorecards (all cycles in the arc)
- `_alire/02_LOGS/Journals/decision_log.jsonl`
- the displayed RETEX(s)
- current `scoring-config.md`

Output: a staged proposal at
`pdca/{scope}/SELF_EVOLVE_PROPOSAL_{date}.md` containing a unified diff +
per-entry rationale. NEVER auto-merged except SAFE-AUTO (below).

## Change classification (BLOCKING gate)

Each proposed diff entry is classified before anything is written:

| Class | Definition | Disposition |
|-------|------------|-------------|
| SAFE-AUTO | Methodology fix that, recomputed against the SAME raw check results of this arc, does NOT raise any cycle's weighted_total. E.g. fix a formula bug, add a stricter check, exclude an all-N/A domain, tighten a threshold. | May auto-apply as one revertible commit tagged `skill-evolve`, IF it cites verifiable evidence. |
| GATED | Anything that raises or could raise any audited score: new lenient threshold, weight shift favoring current state, removing a currently-FAILing check, raising a baseline, re-including an excluded domain. | Written to the proposal file ONLY. Requires explicit user approval. Never auto. |
| FORBIDDEN | Editing a score value directly; lowering `--target` to meet it; excluding a MEASURED (non-N/A) domain; retro-editing a past scorecard to a higher number; deleting a failing test/check to make a domain PASS. | Rejected. Logged. Not even written as a proposal. |

## Anti-gaming invariants (ALL BLOCKING)

1. **No upward self-move.** Recompute the current arc's weighted_total
   with the proposed config against the UNCHANGED raw check results. If
   any cycle's total rises -> the entry is GATED, never SAFE-AUTO. A
   skill that can raise its own score unattended is forbidden by
   construction.
2. **Evidence or nothing (R18).** Every entry MUST cite a verifiable
   artifact: incident date + command output, or a RETEX/decision_log
   reference. "Improves accuracy" / "more representative" without a
   reproducible fact is auto-rejected.
3. **Target is immutable.** SELF-EVOLVE may never read or write
   `--target` / `target`. Only the user changes it.
4. **Provenance ledger.** Append every proposed/applied/rejected entry
   to `_alire/02_LOGS/Journals/SELF_EVOLUTION_LEDGER.jsonl` (append-only)
   AND `decision_log.jsonl`. Schema:
   `{ts, scope, class, change, evidence_ref, recomputed_delta, disposition}`.
5. **Reversibility.** Applied SAFE-AUTO = exactly one commit, message
   prefix `skill-evolve:`, no other files. Trivially `git revert`-able.
6. **Human override wins.** `--no-evolve` disables. A user "reject" on a
   GATED entry is final and logged; the skill must not re-propose the
   same entry for 5 cycles (anti-nag).

## Drift detector (loop-safety, BLOCKING)

Track in the ledger: count of consecutive cycles whose SELF-EVOLVE pass
produced a GATED (score-raising) proposal. If `>= 3` consecutive:
HARD STOP the phase, emit
`SELF_EVOLVE_DRIFT_ALERT` in the RETEX, and require explicit user
acknowledgement before SELF-EVOLVE may run again. Rationale: a skill
repeatedly trying to loosen its own scoring is the exact failure mode
this design exists to prevent.

## What it is good at (legit use)

- Methodology defects that systematically distort ALL audits, not the
  current one: the benchmark_parity N/A=50 anchor (already fixed by
  hand) is the canonical SAFE-AUTO example -- it LOWERS nothing it
  should not and removes an arbitrary number (R18). Recomputed delta
  for the arc: it RAISED backend-go (N/A removed) -> therefore that
  specific fix would have been GATED, not SAFE-AUTO. Correct: a human
  approved it. The phase would have surfaced it instead of it being
  missed for 5 cycles.
- Adding a newly-learned check (e.g. "OPTIONS must not 405" became a
  test convention in cycle 4 -> propose adding TST-09 to the config):
  SAFE-AUTO if it does not raise existing scores (a new check starts
  unmeasured, neutral or stricter).

## What it must never become

- A path to "the score should be 90" by editing weights/baselines.
  That intent is exactly invariant #1's target. The legitimate way to
  90 is real work on the code (e.g. backend-go: fix the 13 failing
  unit tests + raise 12.2% coverage), never a config nudge.

## Integration point

`/audit-pdca ... --evolve` -> after RETEX display, run SELF-EVOLVE:
1. derive candidate diffs from RETEX/decision_log
2. classify each (SAFE-AUTO / GATED / FORBIDDEN)
3. recompute arc totals under proposed config (invariant #1)
4. write proposal file + ledger entries
5. auto-apply ONLY SAFE-AUTO entries (one `skill-evolve:` commit)
6. surface GATED entries to the user for explicit decision
7. run drift detector; HARD STOP + alert if >=3 consecutive GATED arcs

Flag default: OFF. Never implied by `--fix`.
