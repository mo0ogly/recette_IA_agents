# Corpus test authority keyring

This directory holds the **TEST signing authority** for the discovery corpus
passports (Contrat 3, `.inspect_ia_agents/passport.json`). It exists so the
discovery attestation axis (trusted / untrusted / unsigned / malformed) can be
exercised against real Ed25519 signatures produced by a known key.

## This is a TEST key, not a secret (R8)

The private seed is **publicly known on purpose**: it is the corpus test
authority, committed in `.env.example`, and must never be treated as a real
secret. The **public** key is committed here so anyone can verify the corpus
passports offline. There is nothing to rotate and nothing to leak -- this key
signs test fixtures only, never a production agent.

## Files

| File | Content |
|------|---------|
| `test-authority.trust.json` | canonical trust file `{ key_id: pubkey_hex }` consumed by `passport verify --trust` and `scan --trust`. `key_id = "test-authority-1"`. |
| `test-authority.pub` | the raw Ed25519 public key hex (human-readable convenience copy). |

## Reproducing the keypair

The 32-byte Ed25519 seed is the SHA-256 of a fixed phrase, so the whole keyring
is reproducible from documentation alone (R4):

```
phrase = "inspect_ia_agents corpus test authority passport seed v1"
seed   = sha256(phrase) = 46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e
```

Derive the public key (matches `test-authority.pub`):

```
python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; seed=bytes.fromhex('46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e'); print(Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw().hex())"
```

Regenerate the seed from the phrase to double-check:

```
python3 -c "import hashlib; print(hashlib.sha256(b'inspect_ia_agents corpus test authority passport seed v1').hexdigest())"
```

## Re-issuing the corpus passports

The signing seed lives in `.env.example` as `INSPECT_IA_AGENTS_PASSPORT_KEY`.
Export it, then issue a passport per positive subject with the `discoveryprobe-inventory`
binary (built with `cd discoveryprobe && cargo build --release`):

```
export INSPECT_IA_AGENTS_PASSPORT_KEY=46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e
BIN=discoveryprobe/target/release/discoveryprobe-inventory
$BIN passport issue corpus/repos/gh-pr-bot/repo --agent-id "acme-dependency-pr-bot[bot]" --tenant acme --scope read_repo,open_pr --delegation "acme-platform-team,human:alice" --exp 2030-01-01T00:00:00Z --key-id test-authority-1 --spiffe-id spiffe://acme/agent/dependency-pr-bot
```

Verify a passport against the committed trust file (must print `{"kind":"trusted"}`):

```
discoveryprobe/target/release/discoveryprobe-inventory passport verify corpus/repos/gh-pr-bot/repo --trust corpus/keys/test-authority.trust.json --now 2027-01-01T00:00:00Z
```

## Which subjects carry a signed passport

Only positive subjects with a valid manifest (identity present) are signed and
trusted: `gh-pr-bot`, `gh-readonly-reporter`, `gh-admin-overreach`,
`gh-supply-chain-compromise`. Their `discovery-ground-truth.json` records
`attestation_status: "trusted"`. The negative subjects stay unsigned on purpose:
`gh-shadow-agent` (no manifest -- passport absent), `gh-invalid-passport`
(malformed manifest), `gh-no-agent` (no agent at all).
