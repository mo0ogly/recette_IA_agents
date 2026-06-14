# infra-syncer (MCP server)

An MCP server that pushes config files and installs webhooks across repos. High
blast-radius writes. Declares identity + capabilities in `.inspect_ia_agents/manifest.json`.

Discovery recette subject: the Manifest/MCP scanner should detect one agent, surface
`push` + `manage_webhook`, rank it the highest of the corpus, and emit a policy.
