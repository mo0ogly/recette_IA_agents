"""LB3 -- recording of a Lane B run (replayable artifact).

A recording captures, per step, the LLM decision and the resulting AgentAction (if any).
It carries no wall-clock of its own (the AgentActions hold logical-clock stamps), so it is
deterministic. Replaying a recording (LB4) reproduces the exact AgentAction log -- this is
how a non-deterministic live run becomes replayable and, after vetting, promotable to a
Lane A golden (LB5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LlmDecision, ReplayLlm

SCHEMA_VERSION = "1.0"


def _decision_to_dict(d: LlmDecision) -> dict:
    # raw provider payload is intentionally omitted: replay needs only the choice.
    return {"kind": d.kind, "tool_name": d.tool_name, "tool_args": d.tool_args, "text": d.text}


def _decision_from_dict(d: dict) -> LlmDecision:
    return LlmDecision(
        kind=d["kind"],
        tool_name=d.get("tool_name"),
        tool_args=d.get("tool_args", {}) or {},
        text=d.get("text", ""),
    )


@dataclass
class RecordedStep:
    decision: LlmDecision
    action: dict | None = None  # serialized AgentAction, or None for a final step

    def to_dict(self) -> dict:
        return {"decision": _decision_to_dict(self.decision), "action": self.action}

    @staticmethod
    def from_dict(d: dict) -> RecordedStep:
        return RecordedStep(decision=_decision_from_dict(d["decision"]), action=d.get("action"))


@dataclass
class Recording:
    agent_id: str
    principal: str
    target_system: str
    goal: str
    provider: str = "stub"
    model: str = ""
    steps: list[RecordedStep] = field(default_factory=list)

    def decisions(self) -> list[LlmDecision]:
        return [s.decision for s in self.steps]

    def actions(self) -> list[dict]:
        return [s.action for s in self.steps if s.action is not None]

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "agent_id": self.agent_id,
            "principal": self.principal,
            "target_system": self.target_system,
            "goal": self.goal,
            "provider": self.provider,
            "model": self.model,
            "steps": [s.to_dict() for s in self.steps],
        }

    @staticmethod
    def from_dict(d: dict) -> Recording:
        rec = Recording(
            agent_id=d["agent_id"],
            principal=d["principal"],
            target_system=d["target_system"],
            goal=d["goal"],
            provider=d.get("provider", "stub"),
            model=d.get("model", ""),
        )
        rec.steps = [RecordedStep.from_dict(s) for s in d.get("steps", [])]
        return rec

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> Recording:
        return Recording.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def replay_backend(recording: Recording) -> ReplayLlm:
    """A ReplayLlm that re-issues the recording's decisions in order (deterministic)."""
    return ReplayLlm(recording.decisions())
