# acme-invalid-pr-bot (broken passport)

Opens pull requests to bump outdated dependencies across `acme/*` repositories.

- Capabilities (implied by code): `read_repo`, `open_pr`
- Passport: PRESENT but INVALID -- `.inspect_ia_agents/manifest.json` exists but
  is missing the whole `agent.identity` object, so it parses as JSON yet fails
  manifest validation.

> inspect_ia_agents recette test subject -- invalid passport. A discovery
> scanner must detect the agent (code fallback) AND surface
> `passport_status = invalid`. A broken manifest must be reported as invalid,
> never silently trusted as a valid declaration of identity and scope.
