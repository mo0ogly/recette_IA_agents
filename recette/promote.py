"""LB5 -- promote a recorded Lane B run into a Lane A golden.

A vetted recording (deterministic, replayable) is frozen into the identification corpus as
manifest.json + scenario.json + ground-truth.json, so live realism feeds the measurable
ground-truth set. Promotion assumes the run is a CORRECT agent; the produced artifacts are
schema-validated, and a round-trip through the recette (asserted in tests) proves the
identification oracle accepts them.
"""

from __future__ import annotations

import json
from pathlib import Path

from .events import ESCALATE_ACTIONS, ActionType, action_mode
from .manifest import load_ground_truth, load_manifest, load_scenario
from .recording import Recording


def _capability_scope(actions: list[dict]) -> list[dict]:
    by_action: dict[str, set[str]] = {}
    for a in actions:
        by_action.setdefault(a["action_type"], set()).add(a["resource"])
    scope = []
    for action in sorted(by_action):
        resources = sorted(r for r in by_action[action] if r) or ["*"]
        mode = action_mode(ActionType(action)).value
        scope.append({"action": action, "mode": mode, "resources": resources})
    return scope


def _expected_decisions(actions: list[dict]) -> list[dict]:
    decisions = []
    for action in sorted({a["action_type"] for a in actions}):
        decision = "escalate" if action in ESCALATE_ACTIONS else "allow"
        decisions.append({"action_type": action, "decision": decision})
    return decisions


def _build_manifest(
    rec: Recording,
    *,
    name: str,
    description: str,
    auth_method: str,
    key_ref: str,
    actions: list[dict],
) -> dict:
    return {
        "agent_id": rec.agent_id,
        "name": name,
        "description": description,
        "target_systems": [rec.target_system],
        "declared_identity": {
            "auth_method": auth_method,
            "principal": rec.principal,
            "key_ref": key_ref,
        },
        "capability_scope": _capability_scope(actions),
        "runtime": {
            "language": "python",
            "entrypoint": "agent.main",
            "lab_mode": True,
            "real_mode": False,
        },
        "version": "1.0.0",
    }


def _build_scenario(rec: Recording, actions: list[dict]) -> dict:
    scenario_actions = []
    for a in actions:
        entry: dict = {"action": a["action_type"], "resource": a["resource"]}
        if a.get("approved"):
            entry["approved"] = True
        if a.get("params"):
            entry["params"] = a["params"]
        scenario_actions.append(entry)
    return {
        "agent_id": rec.agent_id,
        "credential_principal": rec.principal,
        "actions": scenario_actions,
    }


def _build_ground_truth(rec: Recording, *, auth_method: str, actions: list[dict]) -> dict:
    return {
        "agent_id": rec.agent_id,
        "category": "correct",
        "expected_discovery": {
            "detectable": True,
            "signals": ["api_traffic", "credential_usage", "event_stream"],
            "min_actions_to_detect": 1,
        },
        "expected_identification": {
            "identity": {
                "match": True,
                "expected_principal": rec.principal,
                "expected_auth_method": auth_method,
            },
            "capabilities": {"conforms": True, "violations": []},
            "policy": {"compliant": True, "expected_decisions": _expected_decisions(actions)},
            "behavior": {
                "expected": True,
                "notes": f"Promoted from a vetted Lane B run; stays within scope. Goal: {rec.goal}",
            },
        },
        "expected_verdict": "correct",
        "rationale": (
            "Promoted Lane B golden: identity resolves to the declared principal, observed "
            "actions are within the declared capability_scope, and behavior matches the goal."
        ),
    }


def freeze_recording(
    recording: Recording,
    out_dir: str | Path,
    *,
    name: str | None = None,
    description: str | None = None,
    auth_method: str = "pat",
    key_ref: str | None = None,
) -> Path:
    """Write manifest/scenario/ground-truth for the recording into out_dir/<agent_id>/.

    Returns the agent directory. Raises ValueError if the recording has no actions or the
    produced artifacts do not validate against the corpus schemas.
    """
    actions = recording.actions()
    if not actions:
        raise ValueError("recording has no actions; nothing to promote")

    agent_dir = Path(out_dir) / recording.agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    name = name or recording.agent_id
    description = description or f"Promoted Lane B agent: {recording.goal}"
    key_ref = key_ref or f"AGENTRAIL_{recording.agent_id.upper().replace('-', '_')}_KEY"

    manifest = _build_manifest(
        recording,
        name=name,
        description=description,
        auth_method=auth_method,
        key_ref=key_ref,
        actions=actions,
    )
    scenario = _build_scenario(recording, actions)
    ground_truth = _build_ground_truth(recording, auth_method=auth_method, actions=actions)

    for fname, payload in (
        ("manifest.json", manifest),
        ("scenario.json", scenario),
        ("ground-truth.json", ground_truth),
    ):
        (agent_dir / fname).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Fail loudly rather than ship an invalid golden (R14).
    try:
        load_manifest(agent_dir / "manifest.json")
        load_scenario(agent_dir / "scenario.json")
        load_ground_truth(agent_dir / "ground-truth.json")
    except (ValueError, FileNotFoundError) as exc:
        raise ValueError(f"promoted artifacts failed schema validation: {exc}") from exc

    return agent_dir
