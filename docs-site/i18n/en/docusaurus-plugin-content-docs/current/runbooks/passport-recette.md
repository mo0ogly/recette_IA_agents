# Runbook -- Signed agent passport (Contrat 3, attestation axis)

How a developer issues, verifies, and recettes a **signed agent passport**
(`.inspect_ia_agents/passport.json`): the FROZEN cryptographic attestation that binds an
agent identity to a mandate chain (up to a human), a permitted action scope, and an
expiry. It is the artifact behind the discovery **attestation axis** (`trusted` /
`untrusted` / `unsigned` / `malformed`), distinct from the inventory's manifest-passport
axis (`present` / `absent` / `invalid`).

> Founding design (source of truth): `docs/plans/2026-07-05-agent-passport-design.md`
> (Contrat 3 "the passport"), derived from the agent-governance firewall spec (NIST
> SP 800-207 PEP/PDP vocabulary). Complement to the inventory recette
> (`docs/runbooks/inventory-recette.md`): the manifest passport states what the agent
> DECLARES; the signed passport states what an AUTHORITY attests.

## What the passport is

The passport is a **signed tuple, frozen between issuance and expiry**: an authority
seals a set of claims (`Claims`) with its Ed25519 key, and nobody can then alter a claim
without breaking the signature. In the firewall spec vocabulary (NIST SP 800-207): the
gateway + proxies (I5) are the **PEP** (Policy Enforcement Point), the deny-by-default
policy engine is the **PDP** (Policy Decision Point); the passport is the **identity
credential** the PEP presents to the PDP to bind an action to an attested identity (I3).
Phase 1 (the recette, below) inspects agents that are NOT running: it creates the
artifact, the inspector, and the oracle. Phase 2 (sketched, out of scope) has the gateway
verify the passport at runtime-agent registration, reusing the SAME crate.

Signed fields (`Claims`): `id`, `tenant`, `delegation` (mandate chain), `scope`
(permitted action families), `exp` (RFC 3339 UTC expiry), `spiffe_id` (optional). The
passport adds two UNSIGNED fields: `signature` (Ed25519 hex) and `key_id` (the
authority's key version, for post-rotation verification). `additionalProperties: false`
-- no attestation data can ride past the signature boundary (schema
`corpus/schemas/agent-passport.schema.json`).

### The canonical signed form (what the signature covers)

The signature covers the **`Claims` only**, never `signature`/`key_id`. The signed bytes
(`agent-passport/src/canonical.rs`) are a compact JSON object, keys in **ascending byte
order**: `delegation`, `exp`, `id`, `scope`, `spiffe_id`, `tenant`. An absent `spiffe_id`
(`None`) is OMITTED (no null key). This frozen form is identical on the Rust side and the
Python oracle side -- the bedrock of the equivalence.

### Two orthogonal axes (never to be confused)

The inventory carries TWO independent axes, each keyed on its own `kind`, never re-derived
from the other:

| Axis | Source | States (`kind`) | What it states |
|------|--------|-----------------|----------------|
| **Manifest passport** | `.inspect_ia_agents/manifest.json` (UNSIGNED) | `present` / `absent` / `invalid` | what the agent DECLARES, and whether its declaration validates the schema |
| **Attestation** | `.inspect_ia_agents/passport.json` (SIGNED) | `trusted` / `untrusted` / `unsigned` / `malformed` | what an AUTHORITY attests, and whether the signature/expiry/delegation hold |

The two are orthogonal: an agent can be a manifest shadow (`absent`) yet carry a `trusted`
credential, or carry a `present` manifest yet be `unsigned`. Neither axis implies the
other; the console shows both badges side by side.

## The exportable `agent-passport` crate

`discoveryprobe/agent-passport/` is a **pure, embeddable Rust lib**: no I/O, no clock (the
clock is an injected input, I4), no mock, no hardcoding. It exposes two functions and
their types.

- **Issue**: `issue(claims: Claims, signing_key: &SigningKey, key_id: &str) ->
  Result<Passport, PassportError>` -- computes the canonical bytes, signs with Ed25519,
  seals the `Passport`.
- **Verify**: `verify(passport: &Passport, trust: &TrustStore, now: &Timestamp, declared:
  Option<&DeclaredScope>) -> Verdict` -- NEVER returns an error and NEVER panics (the
  crate's fail-safe boundary). A `Verdict` is either `Trusted` or `Untrusted { reasons }`
  with ALL applicable reasons, accumulated then sorted (replay-stable verdict, I4).

The untrust reasons (`UntrustReason` enum, kind-tagged in snake_case):

| Reason (`kind`) | Meaning |
|-----------------|---------|
| `bad_signature` | the Ed25519 signature does not verify against the trusted key |
| `expired` | `exp <= now` (expired at exactly `exp`) |
| `empty_delegation` | the mandate chain is empty -- no principal at all |
| `no_human_principal` | the chain does not terminate on a human (terminal entry starts with `human:` OR contains `@`) |
| `scope_overreach` | the declared scope requests families absent from the signed scope -- carries `extra` (the missing families, sorted) |
| `unknown_key_id` | the `key_id` is absent from the trust store; the signature could not be checked |
| `malformed_field` | a field could not be interpreted -- carries `field` (e.g. `exp`) |

This is the phase-2 hook: the gateway will reuse `verify` for a deny-by-default on
`untrusted`/`unsigned`/`absent`.

## Issuance -- `passport issue`

The pure crate's I/O consumer is the `discoveryprobe-inventory` binary. The `passport
issue` subcommand reads the Ed25519 signing seed (32-byte seed, hex = 64 characters) from
the `INSPECT_IA_AGENTS_PASSPORT_KEY` environment variable (never logged or echoed, R8),
seals the claims, and writes the passport.

```
discoveryprobe-inventory passport issue <tree> --agent-id <id> --tenant <t> --scope <a,b,c> --delegation <x,human:alice> --exp <rfc3339> --key-id <k> [--spiffe-id <spiffe://...>] [--out <file>]
```

| Flag | Role |
|------|------|
| `<tree>` | the agent tree (default output root) |
| `--agent-id` | agent identifier (`id`) -- REQUIRED |
| `--tenant` | owning tenant -- REQUIRED |
| `--scope` | permitted action families (CSV) -- REQUIRED |
| `--delegation` | mandate chain (CSV, terminates on a human) -- REQUIRED |
| `--exp` | RFC 3339 UTC expiry -- REQUIRED |
| `--key-id` | the sealing authority's key version -- REQUIRED |
| `--spiffe-id` | optional SPIFFE identity (`spiffe://...`) |
| `--out` | output file (default: `<tree>/.inspect_ia_agents/passport.json`) |

Fail-safe: the seed is resolved and the passport sealed+encoded BEFORE any filesystem
write -- no passport file is ever produced on an error path. Exit codes: 0 success, 2
usage, 1 other.

Example (corpus test authority, public seed from `.env.example`):

```
export INSPECT_IA_AGENTS_PASSPORT_KEY=46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e
discoveryprobe/target/release/discoveryprobe-inventory passport issue corpus/repos/gh-pr-bot/repo --agent-id "acme-dependency-pr-bot[bot]" --tenant acme --scope read_repo,open_pr --delegation "acme-platform-team,human:alice" --exp 2030-01-01T00:00:00Z --key-id test-authority-1 --spiffe-id spiffe://acme/agent/dependency-pr-bot
```

> Key source (R18): the seed lives in `.env`; the corpus test key is **publicly known**
> in `.env.example` (a test authority, nothing to run, nothing to rotate -- it only signs
> fixtures). See `corpus/keys/README.md`.

## Verification -- `passport verify`

The fail-safe verifier reads an EXISTING passport, loads a trust file (`--trust`, a JSON
object `{ "<key_id>": "<pubkey_hex>", ... }`) into a `TrustStore`, and checks it against
an INJECTED clock (`--now`, I4 -- never `SystemTime::now`) and an optional declared scope
(`--declared`).

```
discoveryprobe-inventory passport verify <tree> --trust <pubkeys.json> --now <rfc3339> [--declared <a,b,c>]
```

| Flag | Role |
|------|------|
| `<tree>` | the tree whose `.inspect_ia_agents/passport.json` is verified |
| `--trust` | the trust file `{ key_id: pubkey_hex }` -- REQUIRED |
| `--now` | the injected RFC 3339 UTC clock for the expiry check -- REQUIRED |
| `--declared` | declared scope (CSV) for the scope-overreach check -- optional |

The verdict JSON is the product (printed either way on stdout); the **exit code is the
gate**:

| Code | Meaning |
|------|---------|
| `0` | `trusted` |
| `3` | `untrusted` (verdict printed with its reasons -- NOT an error) |
| `2` | usage/config error (bad flag, unreadable/malformed `--trust`, invalid `--now`) |
| `1` | io/other (passport absent or unparseable) |

Example -- verified against the committed trust file (must print `{"kind":"trusted"}`):

```
discoveryprobe/target/release/discoveryprobe-inventory passport verify corpus/repos/gh-pr-bot/repo --trust corpus/keys/test-authority.trust.json --now 2027-01-01T00:00:00Z
```

### Scope overreach only shows up with `--declared`

The scope check is the ONLY one that depends on `--declared`. A BARE `verify` (no
`--declared`) only checks signature + expiry + delegation. For
`gh-passport-scope-overreach`, that yields `trusted` (exit 0). Passing the manifest's
actions (`read_repo,push`) via `--declared`, the passport whose signed scope only covers
`read_repo` becomes `untrusted` with reason `scope_overreach`, `extra ['push']` (exit 3):

```
discoveryprobe/target/release/discoveryprobe-inventory passport verify corpus/repos/gh-passport-scope-overreach/repo --trust corpus/keys/test-authority.trust.json --now 2027-01-01T00:00:00Z --declared read_repo,push
```

The subject's ground-truth `attestation_status: "untrusted"` REFLECTS the
verify-with-declared verdict; the oracle applies the manifest capabilities as the declared
scope.

## The attestation axis in scan + the API

### `scan --trust --now`

The `scan` subcommand now emits an `attestation` per agent (orthogonal to the
manifest-passport axis). It is computed like `passport verify` but with `declared = None`
(the scan covers signature/expiry/delegation, never scope-overreach -- that one needs the
declared capabilities, out of the scan's scope):

```
discoveryprobe-inventory scan <path> [--capture <file.json>] [--team <dir>] [--out <file>] [--trust <pubkeys.json>] [--now <rfc3339>]
```

Without both `--trust` AND `--now`, a present `passport.json` is the fail-safe `untrusted`
(`unknown_key_id`): the scan NEVER claims `trusted` without an injected keyring. I4:
`--now` is the only clock.

The scan model's `Attestation` carries four states: `trusted`, `untrusted { reasons }`,
`unsigned` (no passport file), `malformed { message }` (file present but
unreadable/unparseable).

### `GET /probe/inventory`

The endpoint (`recette/api/routers/probe.py`) runs a live on-demand scan on each tree
under `corpus/repos/*/repo`. When the corpus trust file exists, it invokes the binary with
`--trust corpus/keys/test-authority.trust.json --now <reference>` so a signed passport can
resolve its attestation. The reference clock is an injected constant (default
`2027-01-01T00:00:00Z`, overridable via `INSPECT_IA_AGENTS_INVENTORY_NOW`, R5): fixed,
never `datetime.now()`, so the attestation verdicts stay deterministic (I4). The trust
file has NO env override -- it is a fixed corpus artifact, not an operator knob. The
`summary` aggregates four attestation counters: `attested_trusted`, `attested_untrusted`,
`unsigned`, `attested_malformed`.

### The console

The `InventoryPanel` (page **Probe**) renders, per agent, an **attestation badge** that is
a SECOND, ORTHOGONAL axis to the manifest-passport badge. It is keyed off
`attestation.kind` ALONE (the four states `trusted` / `untrusted` / `unsigned` /
`malformed`). The `untrusted` badge surfaces its typed reasons (the WHY, with
`scope_overreach`'s `extra` and `malformed_field`'s `field`); the `malformed` badge
surfaces its read/parse message.

## The corpus subjects + the equivalence oracle

Four `trusted` positives + three mono-axis negatives (R20) exercise the attestation axis.
Only positives with a valid manifest (identity present) are signed and trusted; their
`discovery-ground-truth.json` records `attestation_status: "trusted"`.

| Subject | attestation_status | Axis (mono) |
|---------|--------------------|-------------|
| `gh-pr-bot` | `trusted` | positive |
| `gh-readonly-reporter` | `trusted` | positive |
| `gh-admin-overreach` | `trusted` | positive |
| `gh-supply-chain-compromise` | `trusted` | positive |
| `gh-passport-expired` | `untrusted` | `expired` |
| `gh-passport-tampered` | `untrusted` | `bad_signature` |
| `gh-passport-scope-overreach` | `untrusted` | `scope_overreach` (verify-with-declared) |

Each negative breaks EXACTLY ONE axis; every other discovery axis stays conform (the
scanner detects the agent, surfaces its action_patterns, emits a policy).

**The equivalence oracle** (`recette/adapters.py::attest_passport`, tested by
`tests/test_passport_equivalence.py`) is a third, independent oracle. The test pins the
equivalence on THREE fronts for every subject carrying a signed passport:

1. the Python oracle's status/reasons == the Rust `passport verify` verdict (driven via
   subprocess on the release binary; if the binary is absent, that leg is skipped, never
   treated as `trusted`);
2. the Python oracle's status == the committed ground-truth `attestation_status` (the
   corpus is the third oracle).

`--declared` is applied on BOTH sides for EVERY subject (the manifest's action families):
without it, Rust would report `trusted` for `gh-passport-scope-overreach` while the oracle
reports `untrusted` -- a false divergence. The Ed25519 check needs the `[bundle]`
(`cryptography`) extra; without it the oracle raises `ImportError` and the crypto asserts
are skipped explicitly, never silently treated as `trusted` (fail-safe I4).

## Fail-safe modes (never fail-open)

- **No keyring** (scan/endpoint without `--trust`/`--now`) -> a present passport is
  `untrusted` (`unknown_key_id`), never `trusted`.
- **Corrupt passport** (present but unreadable/unparseable at scan time) -> `malformed`.
- **Absent passport** -> `unsigned`.
- **`key_id` unknown to the trust store** -> `unknown_key_id`, signature not checked.
- **`cryptography` absent** (Python oracle) -> `ImportError`, crypto asserts skipped, never
  `trusted` by default.

When in doubt, attestation closes (`untrusted`/`unsigned`/`malformed`), never `trusted`.

## Reproducing the test keyring

The 32-byte seed is the SHA-256 of a fixed phrase, so the whole keyring is reproducible
from documentation alone (R4):

```
phrase = "inspect_ia_agents corpus test authority passport seed v1"
seed   = sha256(phrase) = 46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e
```

Regenerate the seed from the phrase:

```
python3 -c "import hashlib; print(hashlib.sha256(b'inspect_ia_agents corpus test authority passport seed v1').hexdigest())"
```

Derive the public key (must equal `corpus/keys/test-authority.pub` and the trust file
value):

```
python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; seed=bytes.fromhex('46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e'); print(Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw().hex())"
```

The committed trust file (`corpus/keys/test-authority.trust.json`) maps
`test-authority-1` -> `83448c3dcc62fd545ec7e6f06a168ea48470ebc1b2630fd49facec0f3b0373cd`.
Full detail: `corpus/keys/README.md`.

## Caveat: DO NOT regenerate `gh-passport-tampered`

`corpus/repos/gh-passport-tampered/` is a **deliberately hand-tampered artifact** (the
`bad_signature` mono-axis negative). It was issued as a valid passport by
`test-authority-1`, then a signed claim was altered AFTER signing (`tenant` changed from
`acme` to `acme-evil` without re-signing). The signature stays a structurally valid
128-hex string (schema-valid) but no longer matches the claims -> `verify` => `untrusted`
reason `bad_signature`.

Running `passport issue` or any regeneration tool on this tree **DESTROYS the test
subject** (it would re-sign the altered claims, erasing the defect). The tree's
`.inspect_ia_agents/DO-NOT-REGENERATE.md` documents it. If overwritten by accident,
restore from git: `git checkout HEAD -- .inspect_ia_agents/passport.json`.

## Building the tool

The binary is produced by the native host build of the `discoveryprobe/` workspace:

```
./recette.sh discovery-build
```

This runs `cargo build --release` and produces
`discoveryprobe/target/release/discoveryprobe-inventory`. The `agent-passport` crate (pure
lib) is a workspace dependency of it.

## Notes

- Determinism (I4): `verify` is a pure function, clock and trust injected; reasons are
  sorted, the serialized verdict is byte-stable. The endpoint pins the reference clock.
- I3: the passport binds an action to an attested agent identity (mandate chain up to a
  human).
- R8: the key lives in the environment (`.env`); the corpus test key is public by design,
  never a production secret.
- The passport is frozen between issuance and expiry: never mutated (a correction = a new
  passport, consistent with I1).
