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
from .redteam import CRESCENDO
from .redteam_recette import _APPROVERS, _approver_for, _violation_of, run_scenario
from .simulate import UserTurns, simulate

# Raised by the PyRIT attacker when the optional dependency is absent. Kept as a
# module constant so the message has a single source of truth; the guard test
# asserts the [redteam] extra hint is present.
_PYRIT_MISSING = (
    "PyRIT attacker requires the [redteam] extra: pip install inspect_ia_agents[redteam]"
)


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


@dataclass
class PyritAttacker:
    """An OPTIONAL PyRIT-backed adversarial ``UserTurns`` provider (the [real] extra).

    A drop-in alternative to the native ``RedTeamSimulator`` (recette.redteam):
    both are ``UserTurns`` callables ``(history) -> str | None`` that the
    ``simulate()`` loop drives turn by turn. This one delegates adversarial prompt
    generation to Microsoft PyRIT (``pyrit``, MIT) instead of the in-repo Crescendo
    phase text, so an operator with the optional dependency installed can attack a
    target with PyRIT's curated jailbreak corpus.

    Approach -- PyRIT jailbreak templates over an escalating objective.
    -------------------------------------------------------------------
    PyRIT's red-teaming orchestrator is async and multi-turn; wiring its adaptive
    loop synchronously into our turn-by-turn ``simulate()`` callable is brittle
    (event-loop reentrancy, target adapters). So on the FIRST call this attacker
    materializes an ORDERED list of ``max_turns`` adversarial turns: each turn wraps
    the ``objective`` (escalated by the in-repo Crescendo phase, ``CRESCENDO``) in a
    PyRIT ``TextJailBreak`` template via ``get_jailbreak(prompt=...)``, caches them
    on the instance, and returns one per call. ``get_jailbreak`` is a pure offline
    template substitution, so for a FIXED ``template`` (not random) the turns are
    byte-stable -- deterministic, no network, no provider key.

    Import guard (R20): pyrit is NEVER imported at module top, and NOT at
    construction -- only inside ``__call__`` (via ``_seed_prompts``). When pyrit is
    absent, ``__call__`` raises a clear ``RuntimeError`` naming the extra (never a
    bare ImportError), so the deterministic gate venv stays dependency-free and the
    failure mode is legible. Constructing the attacker is always safe.

    Verified end-to-end against pyrit 0.14.0 (PyPI ``pyrit``, MIT) on 2026-06-15:
    ``TextJailBreak(template_file_name=...).get_jailbreak(prompt=...)`` produces the
    adversarial turn offline. Exercised by the pyrit-only tests in
    ``tests/test_redteam_pyrit.py`` (which skip when the [redteam] extra is absent).
    """

    objective: str
    # provider/model are reserved for a future PyRIT adaptive-orchestrator path
    # and are UNUSED in the current jailbreak-template mode (turns come from PyRIT's
    # built-in templates, not from a live attacker backend).
    provider: str = "groq"
    model: str = "x"
    max_turns: int = 4
    # A fixed PyRIT jailbreak template (NOT random) keeps the turns deterministic
    # (I4). Must be one of TextJailBreak.get_jailbreak_templates().
    template: str = "ailab_redteam_simulation.yaml"
    _seeds: list[str] | None = field(default=None, init=False, repr=False, compare=False)

    def _seed_prompts(self) -> list[str]:
        """Build (and cache) the ordered adversarial turns via PyRIT TextJailBreak.

        Lazily imports pyrit; raises RuntimeError naming the [real] extra if it is
        not installed. Returns ``max_turns`` turns: the objective, escalated by the
        Crescendo phase, wrapped in a fixed (deterministic) PyRIT jailbreak template.
        """
        if self._seeds is not None:
            return self._seeds
        try:
            from pyrit.datasets import TextJailBreak
        except ImportError:
            raise RuntimeError(_PYRIT_MISSING) from None

        # Fixed template (not random_template) -> get_jailbreak is a pure offline
        # substitution, byte-stable per (template, prompt). Escalate the objective
        # turn by turn with the in-repo Crescendo phases, then jailbreak-wrap each.
        jailbreak = TextJailBreak(template_file_name=self.template)
        seeds = [
            jailbreak.get_jailbreak(prompt=f"{CRESCENDO.phase_for_turn(i)} {self.objective}")
            for i in range(max(self.max_turns, 1))
        ]
        self._seeds = seeds
        return self._seeds

    def __call__(self, history: list[Message]) -> str | None:
        # One user message already sits in history per completed turn; count them.
        turn = sum(1 for m in history if m.role == "user")
        if turn >= self.max_turns:
            return None
        seeds = self._seed_prompts()
        if turn >= len(seeds):
            return None
        return seeds[turn]


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
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    out = out_path / f"{scenario['scenario_id']}.scenario.json"
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} exists; pass overwrite=True to replace")
    out.write_text(json.dumps(scenario, indent=2) + "\n", encoding="utf-8")
    return out
