"""Generate the live broker's agents manifest (the capture allowlist).

The privileged eBPF broker matches a captured process to an agent by its kernel
``comm`` (``discoveryprobe-broker``'s ``comm_marker``). The process-mode launcher
(:mod:`recette.agent_proc`) sets ``comm`` to the agent id via
``prctl(PR_SET_NAME)`` BEFORE the run, so the ``connect`` events captured during
the run carry that name -- a manifest keyed ``comm_marker = agent_id[:15]``
therefore matches the connect surface. (A pid-based match would be more precise
and is the tracked follow-up; this comm path needs no broker change.)

Pure and deterministic (I4): same agent ids -> same manifest, sorted.
"""

from __future__ import annotations

import json
from pathlib import Path

# The kernel truncates ``comm`` to TASK_COMM_LEN (16 incl. NUL) -> 15 usable bytes.
_COMM_MAX = 15


def build_manifest(agent_ids: list[str], *, max_duration_ms: int = 5000) -> dict:
    """A broker manifest allowlisting each agent by ``comm_marker = id[:15]``.

    Duplicate/blank ids are dropped; the result is sorted for a byte-stable file.
    """
    agents = {aid: {"comm_marker": aid[:_COMM_MAX]} for aid in sorted({a for a in agent_ids if a})}
    return {"max_duration_ms": max_duration_ms, "agents": agents}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", help="comma-separated agent ids")
    parser.add_argument(
        "--from-config",
        help="read agent ids from a config json (agents[].id); the launcher uses "
        "this to auto-build the watch-list from every configured agent",
    )
    parser.add_argument(
        "--from-surface-corpus",
        action="store_true",
        help="read agent ids from the surface corpus ground-truth (the subjects "
        "the REPLAY broker knows); the launcher uses this so the passive watch "
        "has a sensible default watch-list in replay mode (no live eBPF)",
    )
    parser.add_argument("--out", required=True, help="output manifest path")
    parser.add_argument("--max-duration-ms", type=int, default=5000)
    args = parser.parse_args(argv)
    ids: list[str] = []
    if args.agents:
        ids += [a.strip() for a in args.agents.split(",") if a.strip()]
    if args.from_config:
        try:
            cfg = json.loads(Path(args.from_config).read_text(encoding="utf-8"))
            ids += [a["id"] for a in cfg.get("agents", []) if a.get("id")]
        except (OSError, ValueError):
            pass
    if args.from_surface_corpus:
        # The replay broker keys its recordings on corpus/surface subject ids;
        # reuse its loader so the watch-list matches exactly what it can replay.
        from .replay_broker import load_reference_surfaces

        ids += list(load_reference_surfaces())
    manifest = build_manifest(ids, max_duration_ms=args.max_duration_ms)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {args.out} ({len(manifest['agents'])} agent(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
