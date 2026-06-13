"""Lab handler registry -- FROZEN in Phase 0 (same 11 names as the catalog).

Maps target_system -> handler module name. The github domain module is named
github_devops to match the catalog module layout.
"""

from __future__ import annotations

HANDLER_MODULES: dict[str, str] = {
    "okta": "okta",
    "github": "github_devops",
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
}
