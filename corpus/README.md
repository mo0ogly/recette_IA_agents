# AgentRail Recette Corpus

Ground-truth corpus of **test agents** used to validate two product tools:

- **discovery** -- must detect/spot each agent.
- **identification / evaluation** -- must judge whether each agent is *correct*.

This repo is the **recette** side of Railgun/AgentRail. It produces the test subjects and
the validation harness, NOT the governance platform. See `.claude/rules/recette-corpus.md`
and the `PERIMETRE COURANT` section of `.claude/CLAUDE.md`.

## What a test agent is

An agent that interacts with **GitHub / GitLab** (open PR/MR, comment issue, read code,
merge, push...). Each agent declares an identity and a capability scope, and carries a
ground-truth describing what the tools should conclude about it.

```
corpus/
  schemas/
    agent-manifest.schema.json    # what the agent DECLARES (identity + capability_scope)
    ground-truth.schema.json      # what the recette EXPECTS (discovery + 4 dimensions + verdict)
  agents/
    correct/<slug>/{manifest.json, ground-truth.json}
    incorrect/<slug>/{manifest.json, ground-truth.json}
```

## The 4 correctness dimensions (identification judges all four)

1. **Identity (I3)** -- the agent is who it claims to be.
2. **Declared vs real capabilities** -- observed actions stay within the declared scope.
3. **Policy conformance** -- actions respect expected allow/deny/escalate.
4. **Behavior** -- the agent acts within its role (no spam, no anomaly).

## Positive AND negative cases (mandatory)

The corpus must contain `correct` agents and deliberately `incorrect` agents. Each incorrect
agent sets a `violation_type`: `identity_mismatch`, `capability_overreach`, `policy_violation`,
`behavior_anomaly`. Without negatives, you cannot prove the identification tool can say "no".

Examples shipped:
- `agents/correct/gh-issue-triager` -- GitHub read+comment bot, fully conformant.
- `agents/incorrect/gl-readonly-overreach` -- GitLab agent declaring read-only but opening
  MRs and pushing (`capability_overreach`).

## Execution target

- **Lab (default)** -- simulated GitHub/GitLab endpoints, no real side effects, reproducible.
- **Real (optional)** -- dedicated test orgs/repos + real tokens (env-provided), for final
  validation. Mode is set per agent via `runtime.lab_mode` / `runtime.real_mode`.

## Recette loop (target)

```
for each agent in corpus:
  run discovery       -> detected? compare to expected_discovery.detectable
  run identification  -> verdict + 4 dimensions? compare to ground-truth
  PASS iff everything matches ground-truth, else FAIL; record the proof
aggregate: detection rate, per-dimension accuracy, false positives / false negatives
```

The harness adapter that invokes discovery + identification (CLI vs HTTP) is wired once the
tools' interface is known.

## Validation

Manifests and ground-truth files validate against the schemas in `schemas/`. Keep
`ground-truth.agent_id` equal to the sibling `manifest.agent_id`.
