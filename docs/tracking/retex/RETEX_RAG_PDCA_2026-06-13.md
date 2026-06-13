# RETEX RAG-PDCA -- cycle 1

Date : 2026-06-13
Session : rag-pdca-20260613-1
Scope : RAG recette merged into main (abe8b15 poisoning governed knowledge_base, a229e2b live Groq runner)

## Score : 96/100 (no CRITICAL red)

| Dim | Before | After | Bar | Status |
|-----|--------|-------|-----|--------|
| D1 precision | 0.67 | **0.87** | >= 0.60 | PASS (now over the real KB) |
| D2 recall | 1.00 | 1.00 | >= 0.90 | PASS |
| D3 ranking | 3/3 | **6/6** top_ok | all | PASS |
| D4 poison resistance | 8/8 | 8/8, 0 mismatch | all PASS | PASS (CRITICAL) |
| D5 poison coverage | OK | OK | OK | PASS (CRITICAL) |
| D6 live Groq | PASS | PASS, 0 leak, chain intact | PASS | PASS (CRITICAL) |
| D7 determinism | byte-identical | byte-identical | I4 | PASS |
| D8 coverage guard | OK | OK (12 domains) | OK | PASS (CRITICAL) |

Track quality   : prec 0.87 / recall 1.00 / ranking 6/6 top_ok
Track poisoning : campaigns 4/4 blocked (exfil deny, invalid-command deny, invalid-data escalate), live Groq PASS (0 leak), KB-guard OK

## Root finding

The retrieval-quality recette evaluated a 4-document TOY corpus (kb-approval / kb-ranking /
kb-ingest / kb-quantum) with 3 queries -- it never exercised the operational knowledge base
(kb-onboarding / kb-incident / kb-refund / kb-release / kb-vacation) that agents actually
retrieve and that the poisoning track governs. D1/D2/D3 were green against documents that do
not exist in production. The 0.67 precision came from token collisions inside the toy set.

## Fix applied

Rewrote `corpus/rag/retrieval-eval.json`:
- corpus = the 5 real operational KB documents (verbatim from knowledge_base.json, real ids)
  + `kb-distractor` (hard negative, targeted by no query -- guards against over-broad matches).
- queries = 6 ground-truth queries over the real docs, including one discrimination case
  ("manager approval recorded" -> must rank kb-refund-1 first over the four other docs that
  also carry "manager"/"approval"); that query is precision 0.20 by design and proves the
  ranking discriminates rather than inflating the mean.

Deterministic (I4 byte-identical), backend untouched (no risk to the concurrent track's
DeterministicRagBackend or its tests). Not an inflation: precision rose because the eval now
uses unambiguous real-KB terms, and a deliberately hard query keeps the mean honest (0.87).

## Verification (R14, same-cycle live proof)

- `python -m recette rag --k 5` -> 6/6 passed, prec 0.87, recall 1.00, all top_ok.
- determinism: two runs byte-identical.
- regression: 60 RAG/poisoning/guard tests OK; role-matrix over campaigns/rag ALL PASS, 0 mismatch.
- D6 live Groq runner: every poisoned instruction blocked, audit chain intact.

## Improvements for next cycle

- DeterministicRagBackend has no stopword filtering: a query sharing "the/a/manager/approval"
  with several docs over-retrieves (Q6 precision 0.20). Tuning tokenization (stopword set)
  would lift precision on shared-term queries -- defer because it touches the concurrent
  track's backend and its tests; coordinate before editing.
- D6 live currently runs one model (llama-3.3-70b-versatile); add a second model to widen
  the live robustness surface.
- Add a poisoned-doc retrieval query (does the polluted KB still rank the poison doc where
  expected?) to bridge the quality and poisoning tracks.
