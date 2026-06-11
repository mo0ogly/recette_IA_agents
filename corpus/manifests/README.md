# Manifest/MCP discovery corpus

Test-agent subjects for the Discovery/Enrichment Plane **Manifest/MCP scanner** -- the
highest-precision surface. Each subject declares identity + capabilities in
`repo/.agentrail/manifest.json`; the scanner reads that manifest directly.

| Subject | Actions | risk_rank | Detected |
|---------|---------|-----------|----------|
| `mcp-readonly-reporter` | read_repo, read_ci | 1 | yes |
| `mcp-pr-bot` | read_repo, open_pr | 2 | yes |
| `mcp-admin-overreach` | push, manage_webhook | 3 | yes |
| `mcp-no-agent` | (none) | 0 | no (true negative) |

The manifest carries `agent.identity.principal`, `agent.target_system` (mcp), and
`agent.capabilities[].action` (canonical actions); an `mcp` block records the server +
tools for realism. The true-negative subject ships only a plain `mcp.json` (no AgentRail
manifest). The offline oracle parses the manifest deterministically (it already handles
the manifest precedence used by every surface).

Ground-truth asserts invariant properties only. Run: `python -m recette discovery --surface mcp`
