"""F1 -- judge a live run's real communication against the agent's declared
manifest, on the 4 recette dimensions (identity, capabilities, policy, behavior).

This connects the visible agent communication (the action log a run produced) to
the OBJECT of the application: deciding whether an agent is correct -- the gap
between what it DECLARES (its config manifest) and what it actually DID.

Determinism (I4): ``judge_run`` is a pure function of (agent config, action log).
It reuses the reference identification adapter; no clock, no random, no I/O. It
computes a read-model verdict on demand and NEVER writes the event store (I1).
"""

from __future__ import annotations

from ..adapters import IdentificationResult, ReferenceIdentificationAdapter
from ..events import AgentAction, mode_for_action


def config_agent_to_manifest(agent_cfg: dict) -> dict:
    """Build the identification manifest the judge expects from a runtime agent
    config. The config declares capabilities as a flat list of action names; each
    becomes a grant whose mode is the canonical read/write mode of that action and
    whose resource scope is unconstrained (the config declares actions, not
    resource globs), so only genuine capability gaps surface as violations."""
    scope = [
        {"action": action, "mode": mode_for_action(action).value, "resources": ["*"]}
        for action in agent_cfg.get("capability_scope", [])
    ]
    return {
        "declared_identity": {"principal": agent_cfg.get("principal", "")},
        "capability_scope": scope,
    }


def judge_run(agent_cfg: dict, action_log: list[AgentAction]) -> IdentificationResult:
    """Judge an action log against the agent's declared manifest (pure, I4)."""
    manifest = config_agent_to_manifest(agent_cfg)
    return ReferenceIdentificationAdapter().identify(manifest=manifest, action_log=action_log)


def action_log_from_run_events(events: list[dict]) -> list[AgentAction]:
    """Extract the executed action log from a run's recorded frames.

    A lane_b run emits a single ``result`` frame carrying ``actions`` (each an
    ``AgentAction.to_dict``); a campaign emits one per ``agent_done`` step's
    recording. Frames without an action list contribute nothing (an inert run --
    e.g. an empty-scope agent -- yields an empty, still-judgeable log)."""
    actions: list[AgentAction] = []
    for frame in events:
        if frame.get("type") != "result":
            continue
        data = frame.get("data") or {}
        for raw in data.get("actions", []) or []:
            if isinstance(raw, dict):
                actions.append(AgentAction.from_dict(raw))
    return actions


def verdict_payload(result: IdentificationResult) -> dict:
    """Serialise an IdentificationResult for the API (the 4 dimensions + typed
    capability violations + the global verdict)."""
    return {
        "verdict": result.verdict,
        "dimensions": {
            "identity": result.identity_match,
            "capabilities": result.capabilities_conform,
            "policy": result.policy_compliant,
            "behavior": result.behavior_expected,
        },
        "capability_violations": [
            {
                "observed_action": v.observed_action,
                "kind": v.kind,
                "note": v.note,
            }
            for v in result.capability_violations
        ],
    }
