"""Process-mode agent launch -- run one Lane B agent as a separate OS process.

The dashboard/campaign launcher runs a Lane B agent IN-PROCESS (inside the API),
so the kernel eBPF tracepoints (`sched_process_exec`, `tcp connect`) see only the
host ``python3`` process, never a per-agent ``comm``. To make the eBPF surface of
the discoveryprobe broker able to ATTRIBUTE an agent, the agent must run as its
own OS process. This module is that entrypoint: it runs the SAME deterministic
Lane B loop the in-process runner uses (``dry_run_lane_b`` -> ``run_lane_b_agent``
+ ``StubLlm`` + in-memory ``LabForge``), so the judged action log is byte-identical
to the in-process run (I4), and emits it as JSON.

It best-effort sets its process ``comm`` to the agent id (``prctl(PR_SET_NAME)``)
so the broker manifest can match it; precise attribution by pid is preferred and
tracked in the design (docs/plans/2026-06-20-ebpf-live-process-mode-design.md).

This is the eBPF-observable run; it is NOT governed (no gateway) -- governance
stays the in-process / API path. Pure-deterministic, no clock, no network beyond
the in-memory lab.

Usage:
    python -m recette.agent_proc --agent-file <agent.json> [--name <comm>]
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from pathlib import Path

# PR_SET_NAME from <linux/prctl.h>: set the calling thread's name (the kernel
# ``comm``, truncated to 15 bytes). Best-effort, Linux-only.
_PR_SET_NAME = 15


def set_process_comm(name: str) -> bool:
    """Set this process's ``comm`` (<=15 bytes) so the eBPF probe can match it.

    Best-effort: returns False on any platform/permission issue without raising
    (observability aid, never a hard dependency of the run)."""
    truncated = name.encode("utf-8")[:15]
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        buf = ctypes.create_string_buffer(truncated)
        return libc.prctl(_PR_SET_NAME, buf, 0, 0, 0) == 0
    except (OSError, AttributeError, ValueError):
        return False


def run_agent_process(agent_cfg: dict) -> dict:
    """Run the agent's Lane B loop in THIS process and return the judged result.

    Reuses ``dry_run_lane_b`` so the output is identical (same engine, same
    StubLlm, same forge) to the in-process API run -- the determinism contract
    (I4) the replay test asserts."""
    from .api.runners import dry_run_lane_b

    return dry_run_lane_b(agent_cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent-file", required=True, help="path to the agent config JSON (one object)"
    )
    parser.add_argument(
        "--name",
        default=None,
        help="process comm to set (default: the agent id); for eBPF attribution",
    )
    args = parser.parse_args(argv)

    agent_cfg = json.loads(Path(args.agent_file).read_text(encoding="utf-8"))
    if not isinstance(agent_cfg, dict):
        print("agent-file must contain a single JSON object", file=sys.stderr)
        return 2

    comm = args.name or str(agent_cfg.get("id") or "agent")
    set_process_comm(comm)

    try:
        result = run_agent_process(agent_cfg)
    except ValueError as exc:
        print(f"agent run rejected: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
