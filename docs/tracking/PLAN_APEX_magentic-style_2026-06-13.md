# Plan : Magentic orchestration style (5th MAF style)
Date : 2026-06-13
Status : TERMINE
Invariants concernes : I3, I4, I6

## Objectif
Add the fifth real MAF orchestration style, magentic, to the recette: a manager
plans + selects the next speaker each round against a progress ledger, with
stall/round limits. Grounded on the real
python/packages/orchestrations/agent_framework_orchestrations/_magentic.py
(StandardMagenticManager, MagenticProgressLedger.next_speaker, max_stall_count=3,
max_round_count; invalid next_speaker terminates).

## Mapping to recette (judged unit = team, style "magentic")
- run = order (sequence of selected next_speakers).
- capabilities = membership (every speaker declared; mirrors "next_speaker not in
  participants" -> invalid) + tool scope.
- behavior = within max rounds (termination.max_hops) AND no stall (the same
  speaker selected >= MAX_STALL=3 times consecutively = no progress).
- identity (I3) / policy (I6): shared per-participant checks.
- Returns the existing IdentificationResult; drive reuses the manager-routed loop
  (same mechanics as group_chat: manager picks speak_<participant>).

## Etapes
- [ ] schema: add "magentic" to the style enum
- [ ] judge: _check_behavior_magentic (bounded rounds + no consecutive stall)
- [ ] drive: route magentic -> manager-routed loop
- [ ] corpus: magentic (1 correct + 1 behavior-stall negative), mono-axis
- [ ] tests: per-style dims + drive/replay + orthogonality
- [ ] docs: replay-model + orchestration runbook + corpus README + Help topic
- [ ] gates: report PASS, full suites green, ruff/mypy/bandit clean

## Resultat
(en cours)
