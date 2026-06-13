# MAF subject corpus (standard-aligned, maf_agent family)

Ground-truth test subjects modelled on the Microsoft Agent Framework declarative
agent (`kind: Prompt`). Part of the unified agent model: each subject is a
`kind: maf_agent` manifest validated against `corpus/schemas/agent-manifest.schema.json`
(the same schema as the git agents), judged on the same four dimensions.

## Layout

```
maf_agents/
  correct/<slug>/      spec.json + actions.json + ground-truth.json
  incorrect/<slug>/    spec.json + actions.json + ground-truth.json
```

- `spec.json`        : what the agent DECLARES (unified manifest, kind=maf_agent):
                       identity (provider/model), tool/handoff capability_scope.
- `actions.json`     : what the agent ACTUALLY did (ordered invoke_tool / handoff log,
                       validated against `maf-actions.schema.json`).
- `ground-truth.json`: what the recette EXPECTS (4 dimensions + verdict, validated
                       against `ground-truth.schema.json`).

## MAF -> recette mapping

| MAF | recette | invariant |
|-----|---------|-----------|
| `tool: mcp` (`server_url`)     | capability invoke_tool, external side effect | I5 |
| `require_approval: always`     | approval=always => escalate, blocks (I6)      | I6 |
| `require_approval: never`/none | approval=never => allow                       | I2 |
| `handoffs` / `agents`          | capability handoff                            | I2 |
| `model.provider` / `model.id`  | declared_identity provider/model              | I3 |

## Coverage rule

At least one correct subject and one incorrect subject per `violation_type`
(`identity_mismatch`, `capability_overreach`, `policy_violation`, `behavior_anomaly`).
Each incorrect subject breaks EXACTLY one dimension (orthogonality), verified by
`tests/test_maf_harness.py`.

## Run

```
python3 -m recette validate    # schema-validate git + MAF + discovery corpus
python3 -m recette maf          # MAF scorecard (4 dimensions)
python3 -m recette report       # unified verdict: identification + MAF + discovery
```

Import a real MAF declarative spec into a draft manifest:

```
python3 -m recette import-maf <spec.yaml> --out corpus/maf_agents/correct/<slug>/spec.json
```
