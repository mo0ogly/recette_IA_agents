# status-reporter (MCP server)

An MCP server that exposes read-only repository/CI status tools. Declares its identity
and capabilities in `.inspect_ia_agents/manifest.json` (the highest-precision discovery surface).

Discovery recette subject: the Manifest/MCP scanner should detect one agent, surface
`read_repo` + `read_ci`, rank it the lowest of the corpus, and emit no policy.
