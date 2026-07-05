# acme-tampered-pr-bot

**IMPORTANT:** This repository contains an **intentionally tampered passport** for corpus testing. The `.inspect_ia_agents/passport.json` file has a deliberate cryptographic defect and **MUST NOT be regenerated** — see `.inspect_ia_agents/DO-NOT-REGENERATE.md` for details. If you run passport regeneration tools on this tree, the test subject will be destroyed.

Opens pull requests to bump outdated dependencies across `acme/*` repositories.

- Identity: GitHub App `acme-tampered-pr-bot[bot]`
- Capabilities: `read_repo`, `open_pr` (write limited to opening PRs)
- Schedule: Mondays 09:00 UTC

## Passport defect (mono-axis: attestation)

The `.inspect_ia_agents/passport.json` was issued as a valid passport by
`test-authority-1` (unexpired, non-empty human-terminated delegation, scope
matching the manifest), then ONE signed claim was altered after signing: the
`tenant` field was changed from `acme` to `acme-evil` WITHOUT re-signing. The
signature is still a structurally valid 128-hex string (schema-valid), but it no
longer matches the tampered claims, so verification fails with reason
`bad_signature`. Expiry, delegation, and scope all conform; this subject
exercises the signature-integrity axis alone.

> inspect_ia_agents recette test subject -- attestation untrusted{bad_signature}.
