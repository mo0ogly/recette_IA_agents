"""Agent-action catalog: the canonical actions an agent can be made to perform.

This is the catalog the cockpit composes an agent's scenario from (read_repo,
open_pr, ...), distinct from the governance action catalog (/catalog/actions).
"""

from __future__ import annotations

from fastapi import APIRouter

from ...tools import agent_action_catalog

router = APIRouter(tags=["agent-actions"])


@router.get("/agent-actions")
def list_agent_actions() -> dict:
    actions = agent_action_catalog()
    return {"actions": actions, "count": len(actions)}
