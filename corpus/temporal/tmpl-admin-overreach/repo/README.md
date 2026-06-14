# infra-syncer (Temporal agent)

A Temporal workflow that pushes config files and installs webhooks across repos.
High blast-radius writes. Deployed as `InfraSyncWorkflow`.

Discovery recette subject: the Temporal scanner should detect one agent, surface
`push` + `manage_webhook`, rank it the highest of the corpus, and emit a policy.
