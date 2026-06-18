"""Lane B agent CLI commands: run / replay / freeze."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _cmd_agent_run(
    manifest_path: str,
    provider: str,
    model: str,
    max_steps: int,
    real: bool,
    enable_writes: bool,
    base_url: str | None,
) -> int:
    from ..lane_b import run_agent
    from ..llm import build_llm

    # Validate the provider/base_url combo before any file read or network call:
    # build_llm raises ValueError when openai_compat is missing its base_url.
    try:
        llm = build_llm(provider, model, base_url=base_url)  # live; key from env (R8)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    spec = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    forge = None  # default = LabForge (no side effects)
    if real:
        from ..realmode import build_real_forge

        forge = build_real_forge(spec["target_system"], enable_writes=enable_writes)
        print(f"REAL MODE on {spec['target_system']} (allowlisted, writes={enable_writes})")
    result = run_agent(
        agent_id=spec["agent_id"],
        principal=spec["principal"],
        target_system=spec["target_system"],
        goal=spec["goal"],
        capability_scope=spec["capability_scope"],
        llm=llm,
        forge=forge,
        provider=provider,
        model=model,
        max_steps=max_steps,
    )
    out = Path(f"{spec['agent_id']}.recording.json")
    result.recording.save(out)
    print(f"ran {len(result.actions)} actions; recording saved to {out}")
    return 0


def _cmd_agent_replay(recording_path: str) -> int:
    from ..lane_b import run_agent
    from ..recording import Recording, replay_backend

    recording = Recording.load(recording_path)
    result = run_agent(
        agent_id=recording.agent_id,
        principal=recording.principal,
        target_system=recording.target_system,
        goal=recording.goal,
        capability_scope=[a["action_type"] for a in recording.actions()],
        llm=replay_backend(recording),
    )
    replayed = [a.to_dict() for a in result.actions]
    deterministic = replayed == recording.actions()
    for a in result.actions:
        print(f"  {a.action_type} {a.resource} (mode={a.mode})")
    print(f"replay deterministic: {deterministic}")
    return 0 if deterministic else 1


def _cmd_agent_freeze(recording_path: str, out_dir: str) -> int:
    from ..promote import freeze_recording
    from ..recording import Recording

    agent_dir = freeze_recording(Recording.load(recording_path), out_dir)
    print(f"promoted to Lane A golden: {agent_dir}")
    return 0
