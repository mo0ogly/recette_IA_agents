# status-reporter (Temporal agent)

A Temporal workflow that reads repository + CI state and emits a status report.
Read-only. Deployed as a scheduled Temporal workflow (`StatusReporterWorkflow`).

Discovery recette subject: the Temporal scanner should detect one agent and surface
`read_repo` + `read_ci` (both read-only), rank it the lowest of the corpus, and emit
no policy (no write capability to constrain).
