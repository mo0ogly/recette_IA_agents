# Policy-bundle contract fixtures

Fixtures for the Ed25519-signed policy bundle the Risk Scoring Engine emits before Railgun.
The recette verifies SHAPE (`corpus/schemas/policy-bundle.schema.json`) + SIGNATURE
(`recette bundle-verify`), it does not produce production bundles.

- `valid/bundle.json` -- a well-formed bundle signed over its canonical payload
  ({policy_version, decisions}, sort_keys, compact separators, utf-8).

The fixture is signed with a **documented test key**: the all-zero 32-byte Ed25519 seed,
whose public key is `3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29`
(a well-known test vector -- it protects nothing and is never a real signing key). Tampered
variants (flipped decision, wrong signature, wrong/substituted key) are generated in-memory
by the tests, so no invalid bundle is committed.

Run: `python -m recette bundle-verify corpus/bundles/valid/bundle.json --pubkey 3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29`
