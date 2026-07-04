# acme-shadow-pr-bot (shadow agent -- no passport)

Opens pull requests to bump outdated dependencies across `acme/*` repositories.

- Capabilities (implied by code): `read_repo`, `open_pr`
- Passport: NONE -- there is no `.inspect_ia_agents/` manifest in this repo.

> inspect_ia_agents recette test subject -- shadow agent. The agent code is
> real (imports the GitHub SDK, opens PRs) but declares nothing: no identity,
> no capability scope, no policy. A discovery scanner must still detect the
> agent from the code AND surface `passport_status = absent` -- an undeclared
> agent is the higher-risk finding, not a silent pass.
