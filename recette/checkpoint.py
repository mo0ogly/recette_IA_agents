"""Checkpoint / time-travel for an orchestration run (aligned with replay, I4).

A checkpoint is a serializable snapshot of a run's decision PREFIX (steps 0..k).
Because ``drive`` is a pure function of the decision stream (recette.orchestrate),
replaying the prefix reproduces the partial run exactly, and resuming with a
different tail backend takes a DIFFERENT branch from that point -- deterministic
time-travel. Mirrors the agent-framework ``_workflows/_checkpoint.py`` concept
(a serializable workflow state you can resume from), kept dependency-free.

- checkpoint(recording, after=k): freeze the first k decisions.
- resume(checkpoint, tail): replay the prefix, then continue with ``tail`` (a
  live backend for a new branch, or a ReplayLlm of the original tail to reproduce).
- partial_run(checkpoint): the run truncated at the checkpoint (prefix only).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LlmBackend, LlmDecision, Message, ToolSpec
from .maf_orchestration import OrchestrationRun
from .orchestrate import OrchestrationRecording, drive

SCHEMA_VERSION = "1.0"


class _ChainedLlm:
    """Returns the prefix decisions in order, then delegates to a tail backend."""

    def __init__(self, prefix: list[LlmDecision], tail: LlmBackend) -> None:
        self._prefix = list(prefix)
        self._tail = tail
        self._i = 0

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        if self._i < len(self._prefix):
            decision = self._prefix[self._i]
            self._i += 1
            return decision
        return self._tail.decide(system=system, history=history, tools=tools)


class _StopLlm:
    """A tail that ends the run immediately (used to truncate at a checkpoint)."""

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        return LlmDecision(kind="final", text="(checkpoint)")


@dataclass
class Checkpoint:
    """A resumable snapshot of a run's decision prefix."""

    team: dict
    prefix: list[LlmDecision] = field(default_factory=list)
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "label": self.label,
            "team": self.team,
            "prefix": [
                {"kind": d.kind, "tool_name": d.tool_name, "tool_args": d.tool_args, "text": d.text}
                for d in self.prefix
            ],
        }

    @staticmethod
    def from_dict(d: dict) -> Checkpoint:
        prefix = [
            LlmDecision(
                kind=x["kind"],
                tool_name=x.get("tool_name"),
                tool_args=x.get("tool_args", {}) or {},
                text=x.get("text", ""),
            )
            for x in d.get("prefix", [])
        ]
        return Checkpoint(team=d["team"], prefix=prefix, label=d.get("label", ""))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> Checkpoint:
        return Checkpoint.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def checkpoint(recording: OrchestrationRecording, *, after: int, label: str = "") -> Checkpoint:
    """Freeze the first ``after`` decisions of a recording as a resumable snapshot."""
    if after < 0:
        raise ValueError("checkpoint 'after' must be >= 0")
    return Checkpoint(team=recording.team, prefix=recording.decisions[:after], label=label)


def resume(cp: Checkpoint, tail: LlmBackend, *, max_steps: int = 64) -> OrchestrationRun:
    """Replay the checkpoint prefix, then continue the run with ``tail``."""
    return drive(cp.team, _ChainedLlm(cp.prefix, tail), max_steps=max_steps)


def partial_run(cp: Checkpoint, *, max_steps: int = 64) -> OrchestrationRun:
    """The run truncated at the checkpoint (the prefix only, nothing after)."""
    return drive(cp.team, _ChainedLlm(cp.prefix, _StopLlm()), max_steps=max_steps)
