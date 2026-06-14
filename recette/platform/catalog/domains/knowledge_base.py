"""knowledge_base domain action specs -- RAG retrieval + index management.

Models a Retrieval-Augmented-Generation knowledge base as a governed system. The
single privileged role is `rag_agent`. Verdict mapping:
- query_knowledge_base is a legitimate retrieval -> ALLOW for rag_agent (the only
  catalog action whose privileged verdict is allow: a read that mutates nothing).
- index-mutating actions (ingest, delete, config, export) -> escalate for rag_agent,
  deny for everyone else. These are the poisoning surface: changing what the RAG
  returns is high blast radius.
- purge_index -> deny for all roles (irreversible wipe).

A poisoned knowledge base cannot bypass this: whatever a retrieved (poisoned)
document instructs, the resulting action is still mediated by the Control Plane.
"""

from __future__ import annotations

from ...events import PolicyVerdict
from ..model import ActionSpec, RiskLevel

TARGET_SYSTEM = "knowledge_base"

_RAG_AGENT = ("rag_agent",)


def _allow(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """Legitimate read row: allow for rag_agent, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_RAG_AGENT,
        description=description,
    )


def _escalate(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """Index-mutating row: escalate for rag_agent, deny for everyone else."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=_RAG_AGENT,
        description=description,
    )


def _deny(action_type: str, risk_level: RiskLevel, description: str) -> ActionSpec:
    """Deny-for-all row: no privileged escape hatch."""
    return ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type=action_type,
        risk_level=risk_level,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description=description,
    )


ACTIONS: tuple[ActionSpec, ...] = (
    _allow(
        "query_knowledge_base",
        RiskLevel.LOW,
        "Retrieve documents from the knowledge base for a query.",
    ),
    _escalate("ingest_document", RiskLevel.MEDIUM, "Add a document into the knowledge base index."),
    _escalate(
        "update_retrieval_config",
        RiskLevel.HIGH,
        "Change retrieval/embedding configuration of the index.",
    ),
    _escalate(
        "export_knowledge_base",
        RiskLevel.HIGH,
        "Export the full knowledge base contents.",
    ),
    _escalate("delete_document", RiskLevel.HIGH, "Remove a document from the knowledge base."),
    _deny("purge_index", RiskLevel.CRITICAL, "Irreversibly wipe the entire knowledge base index."),
)
