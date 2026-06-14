# dependency-pr-bot (Temporal agent)

A Temporal workflow that reads repositories and opens dependency-bump pull requests.
Bounded write (PR creation only). Deployed as `DependencyPrBotWorkflow`.

Discovery recette subject: the Temporal scanner should detect one agent, surface
`read_repo` + `open_pr`, rank it above the read-only reporter, and emit a policy
constraining it to PR creation.
