"""Persisted, replayable red-team / simulation runs + a step-through view.

Unblocks the console red-team/simulation view: a live, LLM-driven conversation is
non-deterministic, so the console never runs one -- it loads a RECORDED run. A
``SimRecording`` freezes a simulate() / red-team outcome (the MAF subject spec, the
transcript, the action log, the per-turn checks, the stop reason) to JSON;
``build_sim_view`` turns it into a render-ready timeline + the four-dimension
verdict (judge_maf). Pure + deterministic (I4); the recording is read-only (I1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .llm import Message
from .maf_judge import MafAction, judge_maf


@dataclass
class SimRecording:
    """A frozen red-team / simulation run, replayable for viewing."""

    spec: dict
    transcript: list[Message] = field(default_factory=list)
    action_log: list[MafAction] = field(default_factory=list)
    stopped_reason: str = "completed"
    checks: list[dict] = field(default_factory=list)  # [{passed, reason}]

    def to_dict(self) -> dict:
        return {
            "spec": self.spec,
            "stopped_reason": self.stopped_reason,
            "transcript": [
                {"role": m.role, "content": m.content, "tool_name": m.tool_name}
                for m in self.transcript
            ],
            "action_log": [
                {
                    "seq": a.seq,
                    "agent_id": a.agent_id,
                    "provider": a.provider,
                    "model": a.model,
                    "action": a.action,
                    "target": a.target,
                    "tool_kind": a.tool_kind,
                    "approved": a.approved,
                }
                for a in self.action_log
            ],
            "checks": self.checks,
        }

    @staticmethod
    def from_dict(d: dict) -> SimRecording:
        transcript = [
            Message(role=m["role"], content=m["content"], tool_name=m.get("tool_name"))
            for m in d.get("transcript", [])
        ]
        action_log = [
            MafAction(
                seq=a["seq"],
                agent_id=a["agent_id"],
                provider=a["provider"],
                model=a["model"],
                action=a["action"],
                target=a["target"],
                tool_kind=a.get("tool_kind"),
                approved=bool(a.get("approved", False)),
            )
            for a in d.get("action_log", [])
        ]
        return SimRecording(
            spec=d["spec"],
            transcript=transcript,
            action_log=action_log,
            stopped_reason=d.get("stopped_reason", "completed"),
            checks=list(d.get("checks", [])),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> SimRecording:
        return SimRecording.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def build_sim_view(recording: SimRecording) -> dict:
    """Render a recorded run as a step-through view + four-dimension verdict."""
    result = judge_maf(recording.spec, recording.action_log)
    return {
        "agent_id": recording.spec["agent_id"],
        "name": recording.spec.get("name", recording.spec["agent_id"]),
        "stopped_reason": recording.stopped_reason,
        "verdict": result.verdict,
        "dimensions": {
            "identity": result.identity_match,
            "capabilities": result.capabilities_conform,
            "policy": result.policy_compliant,
            "behavior": result.behavior_expected,
        },
        "turns": [
            {"index": i, "role": m.role, "content": m.content}
            for i, m in enumerate(recording.transcript)
        ],
        "actions": [
            {
                "seq": a.seq,
                "agent": a.agent_id,
                "action": a.action,
                "tool_kind": a.tool_kind,
                "target": a.target,
                "approved": a.approved,
            }
            for a in recording.action_log
        ],
        "checks": list(recording.checks),
    }
