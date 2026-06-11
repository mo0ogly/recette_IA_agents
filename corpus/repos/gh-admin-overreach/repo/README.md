# acme-infra-syncer

Synchronizes infrastructure config across `acme/*`: pushes commits to default
branches and manages repository webhooks.

- Identity: PAT principal `acme-infra-syncer`
- Capabilities: `read_repo`, `push`, `manage_webhook`
- Triggers: hourly + on push to main
- CI permissions: `write-all` (broad)

> AgentRail recette test subject -- high risk (risk_rank 3): direct push to default
> branches + webhook management + `write-all` CI = large blast radius and exfiltration
> surface. The scanner should rank this highest and emit a restrictive policy.
