"""Live red-team recorder: turn an attack run into a replayable Phase-1 scenario.

A red-team operator attacks a (possibly real) MAF subject and wants the run
frozen into a deterministic sim-scenario that replays byte-stable (I4). Two
pieces:

- ``RecordingLlm`` wraps any ``LlmBackend``, forwards ``decide()`` unchanged, and
  records each ``LlmDecision`` in order. ``program()`` emits the recorded
  decisions as ``subject_program`` step dicts (the scripted form a ``ReplayLlm``
  consumes), so a live run becomes a deterministic replay program.

- ``record_scenario`` drives ``simulate()`` with a RecordingLlm-wrapped subject,
  judges the resulting action log, assembles a schema-valid scenario (target_spec
  + scripted attack turns + recorded program + derived expected verdict), and
  ROUND-TRIPS it through Phase-1 ``run_scenario`` to assert the frozen scenario
  replays to the recorded verdict. The function is pure/deterministic given a
  deterministic backend: no clock, no random, no direct IO.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .judge import judge_subject
from .llm import LlmBackend, LlmDecision, Message, ToolSpec
from .manifest import validate
from .redteam_recette import _APPROVERS, _approver_for, _violation_of, run_scenario
from .simulate import UserTurns, simulate


@dataclass
class RecordingLlm:
    """Wrap an ``LlmBackend``, forward ``decide()`` and record each decision (I4).

    ``program()`` returns the recorded decisions as ``subject_program`` step
    dicts -- the scripted form a ``ReplayLlm`` replays -- so a live attack run
    can be frozen into a deterministic Phase-1 scenario.
    """

    inner: LlmBackend
    recorded: list[LlmDecision] = field(default_factory=list)

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        decision = self.inner.decide(system=system, history=history, tools=tools)
        self.recorded.append(decision)
        return decision

    def program(self) -> list[dict]:
        """Emit the recorded decisions as schema-valid subject_program steps."""
        steps: list[dict] = []
        for decision in self.recorded:
            step: dict = {"kind": decision.kind}
            if decision.tool_name is not None:
                step["tool_name"] = decision.tool_name
            if decision.kind == "final":
                step["text"] = decision.text
            steps.append(step)
        return steps


def record_scenario(
    *,
    spec: dict,
    subject: LlmBackend,
    user_turns: UserTurns,
    scenario_id: str,
    name: str,
    strategy: str = "crescendo",
    approver: str = "deny_all",
    tags: dict[str, str] | None = None,
    max_tool_steps: int = 6,
    max_user_turns: int = 8,
) -> dict:
    """Run an attack against ``subject`` and freeze it as a replayable scenario.

    Wraps ``subject`` in a ``RecordingLlm``, drives ``simulate()`` with the
    scripted attack turns and the named approver, judges the action log to derive
    the expected verdict and broken dimension, and assembles a schema-valid
    sim-scenario (validated as ``sim_scenario``). It then ROUND-TRIPS the frozen
    scenario through Phase-1 ``run_scenario`` (I4 self-check): the recorded
    subject program must replay to the same verdict the live run produced.

    Pure + deterministic given a deterministic ``subject`` backend: it calls only
    ``simulate``, ``judge_subject`` and ``run_scenario`` (all deterministic), with
    no clock, random or direct IO. Raises ``ValueError`` if the assembled scenario
    is schema-invalid or does not replay to the recorded verdict.
    """
    if approver not in _APPROVERS:
        raise ValueError(f"unknown approver {approver!r}; known: {sorted(_APPROVERS)}")
    rec = RecordingLlm(subject)
    result = simulate(
        spec=spec,
        subject=rec,
        user_turns=user_turns,
        approver=_approver_for(approver),
        max_tool_steps=max_tool_steps,
        max_user_turns=max_user_turns,
    )

    attack_turns = [m.content for m in result.transcript if m.role == "user"]

    judged = judge_subject(spec, result.action_log)
    verdict = judged.verdict
    violation_type = _violation_of(judged)

    scenario = {
        "scenario_id": scenario_id,
        "name": name,
        "strategy": strategy,
        "target_spec": spec,
        "attack": {"user_turns": attack_turns},
        "subject_program": rec.program(),
        "approver": approver,
        "tags": dict(tags or {}),
        "expected": {"verdict": verdict, "violation_type": violation_type},
    }

    errors = validate("sim_scenario", scenario)
    if errors:
        raise ValueError(f"recorded scenario invalid: {errors}")

    out = run_scenario(scenario)
    # I4 self-check: the frozen scenario must replay to the verdict the live run produced.
    if out.verdict != verdict:
        raise ValueError("frozen scenario does not replay to the recorded verdict")

    return scenario


def write_scenario(scenario: dict, out_dir: str | Path, *, overwrite: bool = False) -> Path:
    """Write a recorded scenario as pretty 2-space JSON named <id>.scenario.json.

    Refuses to clobber an existing file unless overwrite=True (a frozen corpus
    artifact is immutable by default, I1). Does NOT validate the scenario shape --
    serialization only; validation is record_scenario's job.
    """
    out = Path(out_dir) / f"{scenario['scenario_id']}.scenario.json"
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} exists; pass overwrite=True to replace")
    out.write_text(json.dumps(scenario, indent=2) + "\n", encoding="utf-8")
    return out
