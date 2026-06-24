"""Lab handler registry -- maps target_system -> handler module name.

The github domain module is named github_devops to match the catalog module
layout. ``gitlab`` is a git-family double (canonical git actions, GitLab-
flavoured) with no governance catalog of its own; it shares the git action
vocabulary with github (recette/tools.py ``_GIT_SYSTEMS``).
"""

from __future__ import annotations

HANDLER_MODULES: dict[str, str] = {
    "okta": "okta",
    "github": "github_devops",
    "gitlab": "gitlab",
    "crm": "crm",
    "finance": "finance",
    "data_platform": "data_platform",
    "slack": "slack",
    "support_desk": "support_desk",
    "cloud": "cloud",
    "hris": "hris",
    "legal_dms": "legal_dms",
    "product_cms": "product_cms",
    "knowledge_base": "knowledge_base",
    "mcp": "mcp",
    "comms": "comms",
    "compliance": "compliance",
    # Honeypot exfil sink (#3): the attacker-controlled egress DESTINATION double.
    # Not a governed business system -- a place a rogue agent can egress data TO so
    # the wire surface + the egress tripwire have a concrete target to observe.
    "shadow_db": "shadow_db",
}
