# acme-overreach-pr-bot

Reads `acme/*` repositories and pushes branch updates while bumping dependencies.

- Identity: GitHub App `acme-overreach-pr-bot[bot]`
- Capabilities (manifest): `read_repo`, `push`
- Schedule: Mondays 09:00 UTC

## Passport defect (mono-axis: attestation)

The `.inspect_ia_agents/passport.json` is a genuine, validly signed passport from
`test-authority-1`: the signature verifies, it is unexpired, and the delegation
ends at a human principal. The defect is a scope gap against the manifest: the
signed passport scope is only `read_repo`, while the manifest declares
`read_repo` AND `push`. The agent therefore acts (`push`) beyond what its signed
passport authorizes.

This axis is exercised by the declared cross-check, not by a bare scan:

- `passport verify <tree> --trust ... --now <t>` (no `--declared`) reports
  `trusted` -- the signature, expiry, and delegation are all fine, and without a
  declared set there is nothing to compare the scope against. This is the
  scan-level (Task 7) view, which passes `declared=None`.
- `passport verify <tree> --trust ... --now <t> --declared read_repo,push`
  (the manifest's actions) reports untrusted with reason `scope_overreach` and
  `extra: ["push"]` -- `push` is declared/performed but absent from the signed
  scope.

The ground-truth `attestation_status` = `untrusted` reflects the
verify-with-declared verdict, which the Task 11 oracle produces by applying the
manifest capabilities as the declared set. Every other axis (signature, expiry,
delegation) conforms; this subject exercises the scope-overreach axis alone.

> inspect_ia_agents recette test subject -- attestation untrusted{scope_overreach}
> (declared-scope verdict; scan-level attestation is trusted).
