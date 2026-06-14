# Lab realistic doubles -- runbook

The lab (`recette/lab/`, served on `:8082` and as `mock_local` servers on
`9101+`) is the simulated side of the 14 external systems an agent acts against.
Each system is a domain double in `recette/lab/domains/<system>.py` with a single
`handle(action_type, resource, payload) -> dict | None` entry point, dispatched
by `recette/lab/mock_server.py` on `POST /{target_system}/execute`.

A double is NOT a stub. For every catalogued action it returns realistic,
business-shaped fields, validates its input the way the real system would, and
stays byte-deterministic so replay (I4) holds.

## The three realism dimensions (every domain honours all three)

1. **Business-shaped success** -- per-action fields a real API returns (a wire
   transfer returns a `transfer_id` + `value_date` + `status`, a bucket policy
   returns `bucket` + `acl` + `exposed`), not `{"status": "simulated"}`.
2. **Input validation -> 422** -- a KNOWN action called with INVALID input (a
   negative amount, malformed IBAN, unknown payee ref, bad currency) raises
   `LabActionError(422, msg)`. The mock server maps it to that HTTP status + an
   error envelope `{"success": false, "error": msg}`.
3. **Deterministic coherence** -- all derived values come from a SHA-256 digest
   of `(domain, action_type, resource, payload)`; no clock, no random, no state.
   The same call always yields the same response (I4).

## The toolkit (do not reinvent per domain)

- `recette/lab/errors.py` -- `LabActionError(status_code, message)`. The third
  handler outcome (beside dict=success and None=unknown action -> 404).
- `recette/lab/domains/_realism.py` -- shared deterministic helpers:
  - `digest(domain, action_type, resource, payload)` -> sha256 hex (the seed).
  - `ref(prefix, dig)` -> stable id like `TRF-1a2b3c4d`.
  - `pick(dig, choices)` -> deterministic choice from a tuple.
  - `derived_int(dig, lo, hi)` -> deterministic int in `[lo, hi]`.
  - `coerce_positive_number(raw)` -> float or None (accepts numeric strings,
    rejects garbage like `"payment_amount"`); use for amount validation.
  - `valid_email(value)` -> bool.
  - `envelope(action_type, resource, dig)` -> the common `{action, resource,
    result_id}` base every success extends.

## The three handler outcomes

| Outcome | Handler returns | Mock server -> |
|---|---|---|
| Success | `dict` (business fields) | `200` + `{"success": true, "data": ...}` |
| Known action, bad input | `raise LabActionError(422, msg)` | `422` + `{"success": false, "error": msg}` |
| Unknown action | `None` | `404` |

## The 14 domains

`recette/lab/domains/__init__.py::HANDLER_MODULES` is the registry:
`cloud, crm, data_platform, finance, github, gitlab, hris, knowledge_base,
legal_dms, mcp, okta, product_cms, slack, support_desk`.

`github`/`gitlab` keep the canonical git read handlers (`read_repo`,
`list_repos`, ...) and enrich the risky write actions. `knowledge_base`
preserves the poisoned-doc query path used by the RAG recette
(`rag-knowledge-base-crud.md`).

## Reload after a domain change (operational gotcha)

A `mock_local` server is a subprocess started once. Editing a domain handler
does NOT hot-reload it -- a stale subprocess keeps serving the old code. After
any domain change, reload the server:

```
curl -s -X POST http://localhost:8090/config/servers/<id>/stop
curl -s -X POST http://localhost:8090/config/servers/<id>/start
```

`./recette.sh platform up` starts a fresh set, so a full restart also picks up
changes. Never hand-launch a server (R19).

## Test one action by hand

```
curl -s -X POST http://localhost:8082/finance/execute -H 'content-type: application/json' -d '{"action_type":"launch_wire_transfer","resource":"acct/ops","payload":{"amount":"4200","currency":"EUR","payee":"ACME Ltd"}}'
```

A bad input returns 422, e.g. `payload.amount = "payment_amount"` ->
`{"success": false, "error": "..."}`. From the console this is the Servers ->
Test panel (`ServerTestPanel.tsx`).

## Composed campaigns over these doubles

`campaigns/multidomain/*.campaign.json` compose the per-domain agents into
governed multi-agent scenarios (4 committed): `ops-readonly-sweep` (allow-path
reads), `insider-exfil-chain` (escalate + deny on evidence deletion),
`prod-sabotage` (deny-by-default), `collab-content-day` (allow + escalate).
They run through the real gateway and assert per-action verdicts:

```
.venv/bin/python scripts/run_multidomain_scenarios.py     # ALL PASS -- 4 campaigns
```

The harness layers the gitlab git-family read actions in memory (gitlab has no
committed governance catalog) and grants them ALLOW for `devops_admin`;
everything else uses the committed catalog baseline. The verdict is ground
truth -- a mismatch means the policy mapping is wrong, never weaken the `expect`.

## Determinism gate

Every handler is a pure function of its inputs (I4). No `time`/`datetime.now`/
`random` in any domain double. The error path is deterministic too: the same
invalid call always raises the same status + message. See
`.claude/rules/determinism-replay.md`.

## Related

- `docs/ARCHITECTURE.md` -- lab topology + governed path diagrams.
- `docs/runbooks/platform.md` -- gateway + lab lifecycle.
- `docs/runbooks/recette-sh.md` -- the single launcher (R19).
- `.claude/skills/recette-campaign-builder/` -- how a campaign verdict is decided.
