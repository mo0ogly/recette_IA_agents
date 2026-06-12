# recette_agentrail

## Track U -- Recette API (U1)

The U1 API exposes every CLI capability -- identification / discovery / Lane B runs,
config, and the agent catalog -- over HTTP plus a WebSocket live event stream. It
reuses the `recette` package directly, defaults to the lab forge (no side effects),
and keeps all secrets in env only (R8). Run it with `make api` (or
`python -m recette.api`). See [docs/runbooks/api.md](docs/runbooks/api.md) for
install, endpoints, and WebSocket usage.