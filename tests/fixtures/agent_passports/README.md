# Runtime agent passport TEST fixtures

Purpose-built, committed TEST fixtures that stand in for a runtime agent
passport store (`data/agent_passports/`, which is gitignored -- R8). Each file
is a frozen, Ed25519-signed `AgentPassport` validating against
`corpus/schemas/agent-passport.schema.json`. They give the admission /
passport-middleware tests a trusted and an untrusted (expired) runtime passport
without touching the gitignored runtime store.

These are TEST fixtures only. They are signed with a PUBLICLY KNOWN test seed
and carry NO real secret (R4 -- reproducible from the documented seed below).

## Files

| File | agent id | exp | verdict at 2030-01-01 |
|------|----------|-----|-----------------------|
| `trusted-agent.json` | `trusted-agent` | 2035-01-01T00:00:00Z (far future) | trusted (exit 0) |
| `expired-agent.json` | `expired-agent` | 2020-01-01T00:00:00Z (past) | untrusted{expired} (exit 3) |

Both: tenant `acme`, scope `read_repo,open_pr`, delegation
`agent:<id>,human:alice` (mandate chain ending at a human), `key_id`
`test-authority-1`.

## Seed source and key

- Signing seed: the publicly-known TEST key `INSPECT_IA_AGENTS_PASSPORT_KEY` in
  `.env.example` at the repo root. It is NOT a secret; it exists so these
  fixtures are reproducible.
- `key_id`: `test-authority-1`. The matching public key / trust anchor lives in
  `corpus/keys/test-authority.trust.json` (used by `passport verify --trust`).

## Reproduce (from the repo root)

Build the CLI, export the seed from `.env.example`, then re-issue with `--out`
writing directly to the fixture path. `passport issue` builds the claims from
the flags; the `<tree>` positional is only the fallback output location, so a
throwaway scratch tree is passed while `--out` overrides the path.

```
cd discoveryprobe && cargo build --release && cd ..
export INSPECT_IA_AGENTS_PASSPORT_KEY=$(grep '^INSPECT_IA_AGENTS_PASSPORT_KEY=' .env.example | cut -d= -f2)
BIN=discoveryprobe/target/release/discoveryprobe-inventory
SCRATCH=$(mktemp -d)
$BIN passport issue "$SCRATCH" --agent-id trusted-agent --tenant acme --scope read_repo,open_pr --delegation "agent:trusted-agent,human:alice" --exp 2035-01-01T00:00:00Z --key-id test-authority-1 --out tests/fixtures/agent_passports/trusted-agent.json
$BIN passport issue "$SCRATCH" --agent-id expired-agent --tenant acme --scope read_repo,open_pr --delegation "agent:expired-agent,human:alice" --exp 2020-01-01T00:00:00Z --key-id test-authority-1 --out tests/fixtures/agent_passports/expired-agent.json
rm -rf "$SCRATCH"
```

## Verify (place the fixture in a temp tree's .inspect_ia_agents/)

`passport verify <tree>` reads `<tree>/.inspect_ia_agents/passport.json`, so a
standalone fixture is verified by copying it into a temp tree first.

```
BIN=discoveryprobe/target/release/discoveryprobe-inventory
T=$(mktemp -d) && mkdir -p "$T/.inspect_ia_agents"
cp tests/fixtures/agent_passports/trusted-agent.json "$T/.inspect_ia_agents/passport.json"
$BIN passport verify "$T" --trust corpus/keys/test-authority.trust.json --now 2030-01-01T00:00:00Z   # {"kind":"trusted"}, exit 0
cp tests/fixtures/agent_passports/expired-agent.json "$T/.inspect_ia_agents/passport.json"
$BIN passport verify "$T" --trust corpus/keys/test-authority.trust.json --now 2030-01-01T00:00:00Z   # untrusted{expired}, exit 3
rm -rf "$T"
```
