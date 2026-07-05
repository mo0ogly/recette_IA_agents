# acme-expired-pr-bot

Opens pull requests to bump outdated dependencies across `acme/*` repositories.

- Identity: GitHub App `acme-expired-pr-bot[bot]`
- Capabilities: `read_repo`, `open_pr` (write limited to opening PRs)
- Schedule: Mondays 09:00 UTC

## Passport defect (mono-axis: attestation)

The `.inspect_ia_agents/passport.json` is a genuine, validly signed passport from
`test-authority-1`: the signature verifies, the delegation chain ends at a human
principal, and the signed scope (`read_repo`, `open_pr`) matches the manifest.
The ONLY defect is temporal -- its `exp` is `2020-01-01T00:00:00Z`, in the past.
Verified at any `--now` after that instant it is untrusted with reason
`expired`. Every other attestation axis (signature, delegation, scope) conforms;
this subject exercises the expiry axis alone.

> inspect_ia_agents recette test subject -- attestation untrusted{expired}.
