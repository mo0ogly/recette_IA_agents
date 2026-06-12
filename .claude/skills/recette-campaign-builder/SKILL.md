---
name: recette-campaign-builder
description: >
  Turn a described agent scenario into a runnable AgentRail recette campaign.
  Use this WHENEVER the user wants to create, add, or convert a recette campaign,
  a governance scenario, or a "what-if" agent sequence into something the gateway
  can score -- e.g. "ajoute une campagne pour X", "transforme ce scenario BNP en
  campagne", "cree un cas de test ou l'agent tente Y", "campagne qui prouve que
  DENY sur Z", "scenario SOC/finance/devops en recette". It maps each action to a
  canonical type + expected verdict (allow/escalate/deny), catalogs any missing
  action, grants the contextual verdict via a policy bundle, writes the campaign
  JSON with objective/teaching/rationale help fields, and validates through the
  deterministic gateway harness (and optionally a live LLM). Reach for it even
  when the user just describes a sequence of sensitive actions and an expected
  outcome without saying the word "campaign".
---

# Recette Campaign Builder

A recette campaign is a JSON document (`campaigns/**/*.campaign.json`) that submits a
scripted batch of governed actions through the real AgentRail gateway. Every action flows
the full path -- policy decide -> deny / escalate -> pending / allow -> execute -- so the
campaign produces a real audit trail and a real approval inbox. With per-action `expect`
assertions it becomes a checkable recette: the runner exits non-zero on any verdict mismatch.

Your job: take a scenario the user describes (a sequence of actions, each with a criticality
and an expected verdict) and produce a campaign that PASSES because the governance is correct,
not because you bent the assertions to fit. The verdict is the ground truth; never weaken an
`expect` to make a run green.

## The model you are targeting

```
campaign = {
  "name": str,
  "objective": str,          # why this campaign exists (help field, off the decision path)
  "teaching": str,           # the lesson it demonstrates (help field)
  "agents": [ {id, runtime:"lab", role, capability_scope, model, system_prompt} ],
  "actions": [ {agent_id, target_system, action_type, resource, payload, expect, rationale} ]
}
```

`expect` is one of `allow | deny | escalate`. `rationale` explains the expected verdict per
action (help field). `objective`/`teaching`/`rationale` are pure documentation -- the engine
ignores them, so they never threaten replay determinism (I4). They exist so a reader (auditor,
RSSI) understands the intent without re-deriving it. Always fill them.

## How the verdict is actually decided (read this before mapping)

The engine (`recette/platform/policy/engine.py`) is a pure function of `(action, role)`:

1. `catalog.get(target_system, action_type)` -- if the action is **not in the catalog**, the
   verdict is **DENY**, full stop. This is the single most important constraint.
2. Otherwise it looks up an explicit policy rule for `(target, action, role)`. A rule carries
   **any** verdict, including `ALLOW`. If no rule matches, it falls to the catalog default
   (`escalate` for the action's privileged role, `deny` for every other role).

Consequences you must design around:

- **A step expecting ALLOW or ESCALATE on a new action_type REQUIRES cataloging that action
  first.** You cannot grant a verdict to an action the catalog does not know.
- **A step expecting DENY on a new action_type works for free** (unknown -> deny). Cataloging
  it is optional (do it only if you want a non-CRITICAL risk level recorded).
- **ALLOW on a sensitive action is a policy-bundle rule, never an engine or catalog change.**
  The catalog stays deny/escalate by default; a scenario bundle grants the contextual ALLOW to
  the right role (e.g. a defensive SOC role, an integration admin).
- **There is no payload/threshold/context logic.** "amount > 5000 -> escalate", "shared prod
  host -> escalate", "unreferenced destination -> deny" are NOT computed. Assert the verdict via
  `(role, action)` and put the contextual justification in `rationale`/`payload`. Do not add
  threshold logic to the engine -- it would break I4.
- **Deny-by-default is a feature to exploit.** For a C1 "denied for everyone" step, pick a role
  that is NOT the action's privileged role; the catalog default then yields DENY with zero rules
  (e.g. an `ops_agent` on `finance/launch_wire_transfer` -> deny, because only `finance_admin`
  escalates).

The 11 committed domains live in `recette/platform/catalog/domains/` (okta, cloud,
github_devops, data_platform, finance, crm, slack, support_desk, hris, legal_dms, product_cms)
-- they map 1:1 to the BNP 11-domain referential. Grep them for existing action_types before
inventing one. See `references/verdict-mapping.md` for the criticality<->verdict cheatsheet and
the BNP dotted-name -> flat catalog-name table.

## Workflow

### 1. Extract the scenario into rows

For each action the user describes, capture: the action (their words), the target system, the
criticality (C1-C4), the expected verdict, and which agent/role performs it. A scenario usually
has one role; manipulated/negative scenarios still use one role whose verdict comes out wrong
"for free" via deny-by-default.

Drop C4 (non-sensitive) steps from the asserted actions -- they are out of the sensitive
referential and an uncatalogued C4 action would be denied by the engine, contradicting an
intended ALLOW. Mention in `objective` that C4 steps are omitted. (If the user insists on
showing a C4 ALLOW, that needs a catalog entry with an allow tier -- confirm before doing it.)

### 2. Map each action to the catalog

Resolve the user's action name to a catalog `(target_system, action_type)`. Use
`references/verdict-mapping.md` for common BNP dotted -> flat mappings (`identity.user.suspend`
-> `okta/suspend_user`, `finance.transfer.execute` -> `finance/launch_wire_transfer`, etc.).
Grep the domain modules to confirm the action exists and what its default verdict is.

Classify each action:
- **exists + default verdict already matches the expectation** -> nothing to do (e.g. a C1
  deny-for-all, or an escalate where your role is the privileged one).
- **exists but needs a different verdict for this role** -> add a bundle rule.
- **missing AND expected allow/escalate** -> add an ActionSpec to the extended catalog AND a
  bundle rule.
- **missing AND expected deny** -> leave it; unknown -> deny.

### 3. Reuse the harness, do not fork it

`scripts/run_bnp_scenarios.py` is the deterministic harness and the template. It builds an
**in-memory extended catalog** (committed catalog + extra ActionSpec for actions the 11 domains
lack, including brand-new domains like `mcp`/`comms`/`compliance`) and a **custom policy bundle**
(`baseline_from_catalog` + your scenario rules) granting the contextual verdicts, then runs every
`campaigns/bnp/*.campaign.json` through `create_app` and checks `expect`.

To add a scenario, edit two tables in that script (or a sibling harness modeled on it):
- `EXTRA_SPECS`: one `_esc_spec(target, action, risk, privileged_role, desc)` or
  `_deny_spec(...)` per missing action.
- `EXTRA_RULES`: one `(target, action, role, PolicyVerdict.X, RiskLevel.Y)` per contextual grant
  (this is where ALLOW for sensitive actions is born).

Keep these as in-memory additions; do NOT edit the committed `catalog/domains/*.py` (it changes
the live catalog for everyone and breaks action-count tests). New BNP-faithful action names go
in `EXTRA_SPECS`, not in a committed domain, unless the user explicitly wants them promoted.

### 4. Write the campaign JSON

Put it in `campaigns/bnp/` (or a scenario-appropriate subdir). One scenario = one file. Fill
`name`, `objective`, `teaching`, one agent (or more), and the actions with `expect` + `rationale`.
Follow an existing file in `campaigns/bnp/` as the shape reference -- they all carry the help
fields. No emoji, English content (R10/R12); the conversation can be French.

### 5. Validate (this is the recette, do not skip it)

Run the deterministic harness and confirm every action matches and the chain is intact:

```
.venv/bin/python scripts/run_bnp_scenarios.py
```

Expect `ALL PASS -- N campaigns`. A mismatch means your verdict mapping is wrong -- fix the
bundle/catalog, never the `expect`. If JSON: `python3 -m json.tool <file> >/dev/null`. Lint any
edited Python with `.venv-pyaudit/bin/ruff check` and `.venv-pyaudit/bin/mypy`.

### 6. Optional: live LLM recette

`scripts/run_bnp_live_all.py` drives a real LLM (Groq) that *proposes* the actions; the gateway
governs them. It builds ToolSpecs directly from each campaign (the Lane B `build_tools` catalog
only knows git-canonical + committed-catalog actions, so new actions are unreachable through it).
Key resolution is the per-backend secret store (`data/backend_secrets.json`, R8) then the env
fallback -- never hardcode a key, never commit one. This is a NON-deterministic demo, not the
replayable recette; `run_bnp_scenarios.py` stays the I4 ground truth.

## Anti-patterns

- Weakening an `expect` to make a red run green. The verdict is the spec; fix the policy.
- Adding `SystemTime`/threshold/payload logic to the decision path (breaks I4).
- Editing committed `catalog/domains/*.py` for a one-off scenario (use `EXTRA_SPECS`).
- Inventing a canonical event field. The schema is fixed (`canonical-event-model.md`).
- Asserting a C4 step that is not catalogued (engine denies it).
- Committing `data/backend_secrets.json` or a `.env` with a key (both gitignored; verify
  `git diff --cached` shows no secret before any commit).

## Files

- `references/verdict-mapping.md` -- criticality<->verdict cheatsheet, BNP dotted->flat names,
  the deny-by-default trick, worked role->verdict examples.
- `scripts/run_bnp_scenarios.py` (repo) -- deterministic harness + the EXTRA_SPECS/EXTRA_RULES
  pattern to copy.
- `campaigns/bnp/*.campaign.json` (repo) -- nine worked examples (7 security + 2 business).
