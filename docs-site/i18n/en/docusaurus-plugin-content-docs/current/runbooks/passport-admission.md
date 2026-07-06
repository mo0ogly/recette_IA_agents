# Runbook -- Runtime passport admission (Phase 2, the I3 gate)

How the gateway **admits** an agent to run and to act: an agent is admitted ONLY
if its signed passport is trusted -- **deny-by-default in enforce mode**. This is
the runtime gate of invariant I3 (identity binding), distinct from the phase-1
STATIC inspection (`docs/runbooks/passport-recette.md`, which inspects agents that
are NOT running: it creates the artifact, the inspector, and the oracle). Phase 2
has the gateway verify that same passport, at the moment a runtime agent asks to
launch and on every action it attempts.

> Founding design (source of truth):
> `docs/plans/2026-07-05-passport-admission-design.md`. Admission REUSES the
> phase-1 attestation oracle (`recette/adapters.py::attest_passport`,
> equivalence-tested against the Rust `agent-passport` crate): the decision is the
> same, only the enforcement point changes (offline inspection -> runtime gate).

## What admission is

Admission folds attestation into a **gate decision** at runtime-agent
registration. The primitive is
`recette/platform/admission.py::admit_agent(passport, declared, trust, now,
enforce) -> AdmissionVerdict`. The verdict carries four fields:

| Field | Meaning |
|-------|---------|
| `status` | the oracle's attestation status: `trusted` / `untrusted` / `unsigned` / `malformed` |
| `reasons` | immutable tuple of typed reasons (the WHY; `{"kind": ...}` plus any `extra`/`field`) |
| `mode` | `observe` or `enforce` (the mode the decision was taken under) |
| `admitted` | `(status == "trusted") or (not enforce)` -- a trusted agent is ALWAYS admitted; a non-trusted agent is admitted ONLY in observe |

The decision is a pure function of its arguments: same passport + same keyring +
same clock => same verdict (I4, replayable verdict). Any oracle error (crypto
absent, exception) falls back fail-safe to `status="untrusted"`,
`reasons=({"kind": "oracle_error"},)` -- never `trusted`.

## The two gates

Admission applies at TWO points, both in the Control Plane (I2/I3):

### 1. Pre-launch gate -- `POST /runs` (lane_b)

On registering a `lane_b` run (`recette/api/routers/runs.py`), the gateway:

1. captures the clock at the boundary (`now = capture_timestamp()` -- I4: an
   ISO-8601 UTC INPUT, read once at the frontier, never in the decision path);
2. loads the agent's runtime passport
   (`load_agent_passport(agent_id, passport_dir)`);
3. computes `admit_agent(passport, capability_scope, trust, now, enforce)`;
4. **ALWAYS audits** an `AGENT_ADMISSION` event (I1), even when a denial follows;
5. in enforce mode, if `status != "trusted"` -> **HTTP 403** (the denial is
   already on the log from step 4);
6. on admission, the response carries `admission: {status, mode, admitted}`.

### 2. Per-action gate -- `PassportAdmissionMiddleware`

`recette/platform/passport_middleware.py` re-attests the acting agent's passport
on EVERY action submitted to the gateway. Its `before(request)` uses
`request.timestamp` -- the action's captured clock (an INPUT, I4) -- as `now`.
That is what lets it catch a passport that **expires mid-run**: the launch gate
saw a valid passport, but a late action is evaluated against its own, newer
timestamp and becomes `untrusted`/`expired`.

- In observe, the middleware NEVER vetoes (the launch gate already audited; the
  run proceeds and the normal deny policy applies).
- In enforce, a non-trusted verdict returns a veto reason
  (`untrusted_passport: <status> <kinds>`); the gateway then records an
  `ACTION_DENIED` event (the action is never executed) carrying `deny_reason` =
  that reason.

The middleware is wired into the gateway by `recette/api/app.py`, from the same
`app.state.passport_*` values as the launch gate -- so it shares the SAME enforce
toggle, the SAME passport directory, and the SAME keyring.

## The two modes

| Mode | Env `INSPECT_IA_AGENTS_PASSPORT_ENFORCE` | Behavior |
|------|-------------------------------------------|----------|
| **observe** (default) | unset or any value != `enforce` | audits + warns, NEVER blocks. The verdict is computed and on the log; the agent runs even without a passport. |
| **enforce** | `enforce` (compared after `strip().lower()`) | deny-by-default: 403 at launch + `ACTION_DENIED` per action for any non-trusted agent. |

`enforce_from_env()` (admission.py) returns `True` iff the env equals `enforce`
(case-insensitive, whitespace stripped); any other value -- or unset -- is the
fail-safe observe default.

### Migration posture

Deploy in **observe** first: the verdict is computed and audited for every
runtime agent, without ever breaking a run. Flip to **enforce** ONLY once every
runtime agent carries a trusted passport (otherwise enforce would brick all
current agents, including the demo -- none has a passport initially). Soft
migration is an explicit scoping choice of the design: strict deny-by-default
from the start was rejected.

## Where a runtime passport lives

- **Runtime passport**: `data/agent_passports/<agent_id>.json`. The directory is
  **gitignored** (`.gitignore`: `data/agent_passports/`) -- only the test
  fixtures under `tests/fixtures/agent_passports/` are versioned
  (`trusted-agent.json`, `expired-agent.json`). Directory override via env
  `INSPECT_IA_AGENTS_PASSPORT_DIR` (default `data/agent_passports`).
- **Trust keyring**: `corpus/keys/test-authority.trust.json` (the
  `{ "<key_id>": "<pubkey_hex>" }` object loaded into the `TrustStore`). Override
  via env `INSPECT_IA_AGENTS_PASSPORT_TRUST`; this default admits the corpus
  passports with no configuration.

### Issue a runtime passport

The signed passport is produced by the `passport issue` subcommand of the
`discoveryprobe-inventory` binary (full detail + signing seed:
`docs/runbooks/passport-recette.md`). Write the output to the runtime location
via `--out`:

```
discoveryprobe-inventory passport issue <tree> --agent-id <id> --tenant <t> --scope <a,b,c> --delegation <x,human:alice> --exp <rfc3339> --key-id <k> [--spiffe-id <spiffe://...>] --out data/agent_passports/<id>.json
```

## The audit (I1)

Each `lane_b` launch appends (append-only, immutable) an `AGENT_ADMISSION` event
(`EventKind.AGENT_ADMISSION = "agent_admission"`) carrying
`{agent_id, status, reasons, mode, admitted}`. **Even a 403 is audited first**:
the denial itself is on the log before the HTTP response leaves.

A per-action denial is an `ACTION_DENIED` event
(`EventKind.ACTION_DENIED = "action_denied"`) whose `deny_reason` starts with
`untrusted_passport` (followed by the status and the reason `kind`s). The action
is never executed.

## The console

- The `POST /runs` response carries the `admission` block. The dashboard renders
  an **admission badge** (`console/src/pages/dashboard/AdmissionBadge.tsx`) keyed
  off `status` (the four states `trusted` / `untrusted` / `unsigned` /
  `malformed`), also showing the `mode` (observe/enforce) and `admitted`. An
  observed-but-non-trusted run thus reads as a WARN (the run happened, the
  passport is not trusted).
- An enforce denial (403) never reaches the badge: there is no run. The denial is
  surfaced at the call site (dashboard error banner) in the legible form
  `Admission refusee (enforce): <detail>` -- the WHY of the refusal, not a raw
  `403` envelope.

## Fail-safe modes (never fail-open)

When in doubt, admission closes (non-trusted -> deny in enforce), never
`trusted`:

- **Oracle/crypto absent** -> `oracle_error` -> non-trusted.
- **Trust keyring absent** -> passport not verifiable -> non-trusted
  (`unknown_key_id`).
- **Passport absent** -> `unsigned` -> non-trusted.
- **Error** (exception in the path) -> `untrusted`, admission denied in enforce.

None of these paths admits an agent in enforce; in observe they are audited and
the run proceeds (the WARN is visible).

## Determinism (I4)

- The launch gate captures the clock once at the boundary
  (`capture_timestamp()`, an INPUT); the decision is a pure function of
  `(passport, declared, trust, now, enforce)`.
- The per-action middleware uses the action's CAPTURED clock
  (`request.timestamp`), never `datetime.now()`. Two replays of the same event
  stream against the same keyring produce the same, byte-stable verdict.

## Notes

- I3: admission binds an agent's execution to an attested identity (mandate chain
  up to a human, carried by the signed passport).
- I2: admission is in the Control Plane -- no agent runs or acts without passing
  the gate.
- R8: veto reasons list only reason `kind`s, never key or signature material.
- The passport is frozen between issuance and expiry: a correction is a new
  passport, never a mutation (consistent with I1).
