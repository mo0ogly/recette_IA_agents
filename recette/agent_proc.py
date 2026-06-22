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
import subprocess  # nosec B404 - spawns our own python child, fixed argv, no shell
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


def _fork_connect_probe(target: str) -> None:
    """Best-effort eBPF fork-surface probe: spawn a CHILD process that makes one
    real TCP connect to ``host:port`` then exits. The child's connect is observed
    by the kernel under the CHILD pid; the sched_process_fork edge links it to
    THIS (parent) process, so the discoveryprobe mapping attributes it to the
    agent via the fork chain. Observability-only: never affects the judged run,
    never raises."""
    try:
        host, _, port = target.partition(":")
        if not host or not port.isdigit():
            return
        child = subprocess.Popen(  # nosec B603 - fixed interpreter, no shell, args from config
            [
                sys.executable,
                "-c",
                "import socket,sys;\n"
                "h,p=sys.argv[1],int(sys.argv[2])\n"
                "try:\n"
                "    s=socket.create_connection((h,p),timeout=2); s.close()\n"
                "except OSError:\n"
                "    pass",
                host,
                port,
            ],
        )
        # Reap it within the capture window without blocking the agent run long.
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
    except (OSError, ValueError):
        return


def run_agent_process(agent_cfg: dict, servers: list[dict] | None = None) -> dict:
    """Run the agent's Lane B loop in THIS process and return the judged result.

    Without a server binding (or no ``servers`` list) this is exactly
    ``dry_run_lane_b`` -- the in-memory ``LabForge``, deterministic (I4), the
    contract the replay test asserts. It makes NO real network I/O.

    With a ``server`` binding AND a ``servers`` registry, the agent runs through
    the real ``ProxyForge`` (HTTP to the bound ``mock_local`` server), so each
    action is a REAL outbound TCP connect -- the only way the kernel eBPF
    ``connect`` tracepoint has anything to attribute (with ``comm`` set to the
    agent id by :func:`set_process_comm`). No gateway here (the process path is
    eBPF-observability, not governance)."""
    from .api.runners import build_stub_llm, forge_for_agent
    from .lane_b import run_agent as run_lane_b_agent

    if not agent_cfg.get("server") or not servers:
        from .api.runners import dry_run_lane_b

        return dry_run_lane_b(agent_cfg)

    for key in ("principal", "target_system", "goal", "capability_scope"):
        if not agent_cfg.get(key):
            raise ValueError(f"agent missing {key!r}")
    scenario = agent_cfg.get("scenario")
    if not scenario:
        raise ValueError("process mode needs a mock scenario")
    if agent_cfg.get("ai_mode", "mock") == "real":
        raise ValueError("process mode is mock-only")
    # gateway=None: a server-bound agent resolves to ProxyForge (real HTTP).
    forge = forge_for_agent(agent_cfg, servers, gateway=None)
    result = run_lane_b_agent(
        agent_id=str(agent_cfg.get("id") or "agent"),
        principal=agent_cfg["principal"],
        target_system=agent_cfg["target_system"],
        goal=agent_cfg["goal"],
        capability_scope=agent_cfg["capability_scope"],
        llm=build_stub_llm(scenario),
        forge=forge,
        stop_on_repeat=True,
    )
    return {
        "actions": [a.to_dict() for a in result.actions],
        "tool_results": result.tool_results,
        "steps": result.recording.to_dict()["steps"],
    }


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
    parser.add_argument(
        "--servers-file",
        default=None,
        help="path to the servers registry JSON (list); enables the real ProxyForge "
        "path so a server-bound agent makes real TCP connects (eBPF connect surface)",
    )
    args = parser.parse_args(argv)

    agent_cfg = json.loads(Path(args.agent_file).read_text(encoding="utf-8"))
    if not isinstance(agent_cfg, dict):
        print("agent-file must contain a single JSON object", file=sys.stderr)
        return 2
    servers: list[dict] | None = None
    if args.servers_file:
        loaded = json.loads(Path(args.servers_file).read_text(encoding="utf-8"))
        servers = loaded if isinstance(loaded, list) else None

    comm = args.name or str(agent_cfg.get("id") or "agent")
    set_process_comm(comm)

    probe = agent_cfg.get("fork_connect_probe")
    if isinstance(probe, str) and probe:
        _fork_connect_probe(probe)

    try:
        result = run_agent_process(agent_cfg, servers)
    except ValueError as exc:
        print(f"agent run rejected: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
