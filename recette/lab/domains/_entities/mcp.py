"""MCP lab entity: tools (derived from name)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "SEED_DISABLED_TOOLS",
    "SEED_TOOLS",
    "McpTool",
    "derive_tool",
]

SEED_TOOLS = ("web_search", "code_interpreter", "file_search")
SEED_DISABLED_TOOLS = ("mcp/tool/disabled-1", "disabled_tool")


@dataclass(frozen=True)
class McpTool:
    """An MCP tool, fully derived from its name."""

    tool: str
    registered: bool
    enabled: bool

    @property
    def usable(self) -> bool:
        """A disabled/unregistered tool cannot be invoked."""
        return self.registered and self.enabled


def derive_tool(tool: str) -> McpTool:
    name = tool or "mcp/tool/unknown"
    disabled = name in SEED_DISABLED_TOOLS
    return McpTool(tool=name, registered=not disabled, enabled=not disabled)
