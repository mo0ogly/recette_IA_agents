# Ghost-detection -- next steps (APEX backlog)

> The wire<->audit ghost-detection bench is DONE (6 scenario steps + 3
> reconciliation phases, live-proven, console UX, raise-to-audit-log). This
> backlog captures what makes that capability go further, as autonomous APEX
> tasks. Each task is self-contained: goal, acceptance, invariants, gates. Do
> them in priority order; none blocks the bench (which already works).

Ground truth in code: `recette/platform/proxy/reconcile.py` (phases 1-3),
`recette/platform/proxy/bypass_event.py` (step 5), `recette/redteam_ghost_probe.py`,
`scripts/smoke_reconcile.py`, `console/src/pages/proxy/ReconcilePanel.tsx`.

## Priority order

1. B -- scored recette subject (makes the bench MEASURABLE, not just demonstrable)
2. C -- LLM host allowlist (closes the real-mode false-positive gap)
3. D -- MAF orchestration ghost (extends to the standard-aligned family)
4. A -- Mehdi feedback loop (coordination; unblocks the real priority)
5. E -- multi-session hygiene (housekeeping)

---

## Task B -- ghost-unmediated-path as a SCORED recette subject (HIGH)

**Goal.** Today reconcile is a console feature + smoke, OUTSIDE the scored
recette. Turn the unmediated-path detection into a ground-truth subject the
external discovery/identification tools are measured against (PASS/FAIL,
accuracy), wired into the coverage guard so a gap is a red test.

**Acceptance.**
- A negative subject (e.g. `corpus/agents/incorrect/ghost-unmediated-writer`)
  whose `violation_type` is the mediation/identity axis (mono-axis, the other 3
  dimensions conform -- `recette-corpus.md`), with a ground-truth that asserts
  the unmediated path MUST be detected.
- The judge is deterministic (I4) and has a replay test.
- `tests/test_coverage_guard.py` turns RED if the new axis is not fully wired
  (no silent gap -- the `no-silent-recette-gaps` lesson).
- `python -m recette run` scores it; a tool that misses the unmediated path is a
  measurable FAIL.

**Invariants.** I4 (deterministic judge + replay), recette-corpus mono-axis,
coverage-guard anti-silence. **Gates.** `./recette.sh test`, `make recette`.

**Design note.** Decide first whether this is an IDENTIFICATION subject (an
action-log carrying an unmediated side effect to judge) or a DISCOVERY subject
(a repo whose manifest declares mediation the code violates). Likely
identification first. Brainstorm before coding (HARD GATE).

---

## Task C -- LLM backend host allowlist (MED)

**Goal.** `build_allowlist(..., llm_hosts=set())` is empty today: a real-provider
run would false-flag LLM traffic on the wire as a bypass. Allowlist the
configured backends' hosts.

**Acceptance.**
- `build_allowlist` receives the LLM hosts derived from the configured
  `ai_backends` (provider -> host:port, e.g. groq -> `api.groq.com:443`).
- `GET /proxy/reconcile` passes them; a real wire flow to an LLM host is NOT a
  bypass.
- Unit test: an LLM-host flow reconciles ok; a non-allowlisted host still flags.
- Map provider -> host in ONE place (R5 config-first), no hardcoded host in the
  decision path.

**Invariants.** I4 (pure), R5 (config-first), R18 (no secret, host only).
**Gates.** `./recette.sh test`, ruff/mypy/bandit.

---

## Task D -- MAF orchestration ghost (handoff to an unmediated/undeclared target) (MED)

**Goal.** Extend detection to the MAF family: a handoff to a target OUTSIDE the
declared `HandoffConfiguration` set, or a tool call escaping mediation, is the
orchestration-level ghost. Crosses the parallel red-team work.

**Acceptance.**
- A MAF orchestration subject (`corpus/maf_orchestration/...`) with a `run.json`
  hop to an undeclared target is judged a `behavior`/mediation violation
  (mono-axis), deterministically (I4).
- Reuses `maf_orchestration.py` semantics (out-of-set transfer is an error, not a
  silent allow -- `maf-standard.md`), not a parallel verdict shape.

**Invariants.** I4, I6 (approval-gated tools), maf-standard mono-axis.
**Gates.** `./recette.sh test`, `make recette`.

---

## Task A -- Mehdi feedback loop (coordination, low code) (MED)

**Goal.** Get the external tool author to exercise the ghost-detection part and
return a verdict on whether the mapping fits his diagram.

**Acceptance.**
- A target runbook `docs/runbooks/ghost-detection-recette.md`: pull, the 6 steps,
  the 3 phases, how to run the smoke + the console tab, what to look for.
- If discovery is in scope: publish a discovery repo subject exposing the
  unmediated-path pattern (`python -m recette publish ...`).
- Capture his verdict (a tracking note), feed gaps back as new tasks.

**Invariants.** R14 (the runbook steps are reproducible), R19 (recette.sh only).
**Gates.** the runbook actually runs end to end once.

---

## Task E -- multi-session hygiene (LOW)

**Goal.** Clear the shared-tree debt without losing work (R21).

**Acceptance.**
- `stash@{0}: proxy-wip-preserve` is confirmed stale (origin already has
  knowledge_base + mcp/comms/compliance/gitlab) and dropped BY THE OWNING SESSION
  (never blind).
- The untracked `corpus/agents/incorrect/rt-prbot-overreach/` is either committed
  (with the `test_recette` expected count bumped) or removed by its author, so
  the suite is green on every tree, not just a fresh clone.

**Invariants.** R21 (no work loss), R20 (no silent recette gap).
**Gates.** `./recette.sh test` green on a dirty AND a clean tree.

---

## Out of scope (named)

- Network ENFORCEMENT (blocking the egress): the platform's job, not this lab.
- Honeypot realism (200 instead of 404): cosmetic; detection works on the wire
  target regardless.
