# calculator (MCP server, NOT an agent)

A plain MCP server exposing arithmetic tools (`mcp.json`). It ships no inspect_ia_agents manifest
and performs no target-system action. True-negative subject: the Manifest/MCP scanner must
not flag it as an agent (false-positive guard).
