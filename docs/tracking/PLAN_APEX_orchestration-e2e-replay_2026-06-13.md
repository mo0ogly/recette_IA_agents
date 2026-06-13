# Plan : End-to-end persistent, replayable orchestration recette + group_chat
Date : 2026-06-13
Status : EN_COURS
Invariants concernes : I3 (identity), I4 (deterministic replay), I6 (approval gate)

## Objectif
Make the multi-agent orchestration work a first-class, end-to-end recette that
integrates with the defined agent-recette + the live-groq runner family:
1. A live LLM (Groq) drives an orchestration team -> a run is produced and
   RECORDED to a persistent artifact (mirrors recette/recording.py).
2. The recording REPLAYS deterministically (ReplayLlm) -> the exact same run ->
   the same four-dimension verdict (I4). No clock, no random in the judge.
3. The recording can be FROZEN into a corpus subject (team/run/ground-truth),
   exactly like the deterministic corpus already shipped -- closing the loop
   dynamic-LLM-run -> deterministic recette subject.
4. Add the group_chat orchestration style (judged + corpus) for coherence with
   the handoff/sequential/concurrent styles already shipped.
5. Wire it into the system: `python -m recette report` already scores the
   orchestration corpus; add a `scripts/run_orchestration_live_groq.py` runner
   in the existing live-groq family, docs, and console Help.

## Grounding (reuse, no invent)
- LlmBackend / LlmDecision / StubLlm / ReplayLlm / GroqLlm (recette/llm.py).
- Recording pattern (recette/recording.py): RecordedStep{decision, emitted}.
- judge_orchestration (recette/maf_orchestration.py): pure (I4).
- freeze pattern (recette/redteam.py to_corpus_subject).
- live-groq runner family (scripts/run_*_live_groq.py). Key: GROQ_API_KEY (R8 env).

## Tool protocol for the driver
Current agent gets, as ToolSpec: its declared tools (name "<kind>:<target>"),
and (handoff/group_chat) one routing tool per allowed next ("handoff:<target>" /
"speak:<participant>"). A tool_call emits a hop / order-entry / ToolCall; a final
decision stops. Sequential/concurrent are structural (each participant once).

## group_chat judging
capabilities = membership (every speaker declared) + tool scope; behavior =
bounded turns (termination.max_hops) and no speaker monopolises (repeat < spam
threshold). Mirrors the existing dimensions.

## Etapes
- [x] judge: add group_chat branch (capabilities membership, behavior bounded+no-monopoly)
- [x] corpus: group_chat (1 correct + 1 behavior negative), mono-axis
- [x] recette/orchestrate.py: drive(team, backend) + OrchestrationRecording (save/load) + replay + freeze_to_corpus
- [x] CLI: `recette orchestrate run|replay|freeze`
- [x] scripts/run_orchestration_live_groq.py (live record loop, GROQ_API_KEY env)
- [x] tests: drive deterministic (stub), record->replay identical run+verdict, freeze round-trips validate+judge, group_chat dims
- [x] docs/runbooks/orchestration-recette.md (live -> record -> replay -> freeze)
- [x] console Help: helpTopics "corpus" + PageHelp on the Corpus page
- [x] gates: report PASS, full backend + console suites green, ruff/mypy/bandit + tsc clean

## Resultat
Done. orchestration 11/11 teams PASS (5 handoff + 2 sequential + 2 concurrent +
2 group_chat). End-to-end pipeline: drive(team, LlmBackend) -> record (decisions
+ run, persistent) -> replay (ReplayLlm reproduces the EXACT run, integrity guard,
then judge -> verdict) -> freeze_to_corpus (dynamic run becomes a deterministic
corpus subject). CLI `recette orchestrate run|replay|freeze`; live runner
scripts/run_orchestration_live_groq.py (GROQ_API_KEY). 708 backend + 206 console
tests green; ruff/mypy/bandit clean; tsc 0 errors. The judge stays pure (I4); all
non-determinism is captured as recorded decisions. Console Corpus page + Help.
