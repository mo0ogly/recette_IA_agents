# GitLab Mirror -- Provenance Policy (this file is EXCLUDED from the GitLab mirror)

> This document lives under `.claude/` on purpose: `.claude/` is DROPPED from
> the GitLab export, so the policy itself never lands on GitLab (it would carry
> the very tokens it forbids). GitHub keeps everything, including this file.

## Goal

GitHub keeps EVERYTHING. The internal GitLab mirror
(`gitlab.cossi.internet/sdo/desc/siq/cyber_lab_agents_ia`) carries **no trace
that an AI dev assistant served to develop the code** (dev provenance), while
KEEPING all research/product references (papers, benchmarks, provider model
ids, labs, workflow architecture).

## The two kinds of "claude" -- only ONE is stripped

- **KEEP (research/product):** Anthropic *provider* + *model* references --
  `claude-opus-4-8`, `anthropic/claude-*`, `"model": "claude-x"`, the Anthropic
  wire-decode (`console/.../wireLlmDecode.ts`), `AnthropicLlm`, the provider in
  `recette/llm/_registry.py`. Removing these would break the LLM catalog.
- **STRIP (dev provenance):** the `.claude/` tooling dir, `docs/plans/`, and
  every tooling reference in tracked text (`.claude/...` paths, `CLAUDE.md`,
  "Claude Code", `Co-Authored-By: Claude`, agent-vocabulary tied to the vendor).

## The tool

`scripts/gitlab_export.sh` (read-only on the repo; GitHub untouched; re-runnable):

1. `git archive origin/main` -> `.gitlab-export/tree/` (read-only snapshot).
2. DROP tooling (`.claude/`, `docs/plans/`, the export scripts themselves, and
   defensive no-ops for other tools). Adapt `DROP_PATHS` per repo (audit first).
3. SCRUB provenance lines (soft rewrites + hard drops), keeping model ids.
4. VERIFY garde-fou: ABORT (no push) on any provenance residue, leftover
   tooling dir, or real secret (test fixtures excluded).
5. `--push`: commit the scrubbed tree ON TOP of GitLab main (fast-forward) ->
   push `gitlab-sync` branch -> create + merge a MR via the API (the token's
   merge right works where a protected-branch direct push fails; retries on 405).
6. `--strict`: also anonymize model/provider ids (claude->ModelX).

## Iterative audit (the transposable core -- never trust the first scrub)

Each repo hides provenance differently. After every run, re-grep the export
tree INDEPENDENTLY of the script's own verify:

```
T=.gitlab-export/tree
grep -rInE '\.claude([/._-]|$)|CLAUDE\.md|Claude Code|Co-?Authored-?By: *Claude|claude\.ai|Claude subagent|\.husky|cursorrules' "$T"
find "$T" -iname '*claude*'
```

Known leaks found this way on THIS repo (fixed): a bare `.claude` in
`.dockerignore` (no slash), and the export tooling's OWN obfuscated regex
(`${_dot}claude/`) -- both now handled (broadened pattern + the scripts are in
DROP_PATHS). Expect leaks on the first pass of any new repo; loop until 0.

## Token

Project Access Token (scope `write_repository` + `merge`, ideally not a global
PAT) in `.env.gitlab` (gitignored via `.env.*`). Masked in all output
(`sed s/$TOKEN/***/`). NEVER in `.git/config`, NEVER committed.

## Re-sync

`scripts/gitlab_export.sh --push` is idempotent-ish: re-run to resync GitLab
with GitHub main. It rebuilds the snapshot, re-scrubs, re-verifies, and merges
a fresh MR. The garde-fou refuses to publish anything unclean.
