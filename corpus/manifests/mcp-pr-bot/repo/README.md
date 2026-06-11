# dependency-pr-bot (MCP server)

An MCP server that reads repositories and opens dependency-bump pull requests. Bounded
write. Declares identity + capabilities in `.agentrail/manifest.json`.

Discovery recette subject: the Manifest/MCP scanner should detect one agent, surface
`read_repo` + `open_pr`, rank it above the reporter, and emit a policy.
