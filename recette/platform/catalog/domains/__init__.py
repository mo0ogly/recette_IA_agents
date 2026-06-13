"""Domain module registry -- FROZEN in Phase 0.

The 11 module names are fixed here so parallel domain workstreams never edit a
shared file: each workstream owns exactly its own module. Adding a domain is a
deliberate registry change, not a side effect.
"""

from __future__ import annotations

DOMAIN_MODULES: tuple[str, ...] = (
    "okta",
    "github_devops",
    "crm",
    "finance",
    "data_platform",
    "slack",
    "support_desk",
    "cloud",
    "hris",
    "legal_dms",
    "product_cms",
    "knowledge_base",
)
