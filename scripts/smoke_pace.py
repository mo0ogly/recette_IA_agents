#!/usr/bin/env python3
"""Live smoke: per-agent pacing actually slows a real run, without changing the
judged output.

Closes the last unproven link for the pacing feature: every other proof is a
unit test (`tests/test_pace.py`, `tests/test_runners.py`,
`tests/test_pace_determinism.py`). This one drives the RUNNING governed API
(POST /runs -> poll GET /runs/{id}) and asserts, end to end:

  1. a server-less lab agent launched with ``pace_ms`` set takes measurably
     LONGER (wall clock) than the same agent at pace 0 -- the ops-layer sleep
     really spaces the actions of a live run;
  2. the action frames emitted by both runs are IDENTICAL (live echo of the
     I4 guarantee: pacing is operational metadata, never on the judged path).

Deterministic: the run uses an injected ``stub_script`` (StubLlm), so no real
provider key is needed and the action log is fixed. Server-less agent (no
``server``) runs the in-memory LabForge path -- it does not depend on any mock
server being up. Re-runnable: the ``smoke-pace-bot`` fixture is deleted up
front and on exit.

Requires a RUNNING governed API (start it with ``./recette.sh platform up``;
never hand-launch -- R19). Stdlib only (urllib).

Usage:
    python3 scripts/smoke_pace.py --api http://127.0.0.1:8090
Exit 0 = SMOKE PASS, exit 1 = failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

AGENT_ID = "smoke-pace-bot"
# Three tool calls -> three recorded steps -> three inter-action sleeps when
# paced. A longer script makes the wall-clock delta unambiguous.
STUB_SCRIPT: list[dict] = [
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/y"}},
    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/z"}},
    {"kind": "final", "text": "done"},
]
PACE_MS = 600
STEPS = 3  # number of recorded actions (the three tool calls)


def _req(method: str, url: str, body: dict | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        return exc.code, (json.loads(raw) if raw else None)


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        print(f"[FAIL] {msg}", file=sys.stderr)
        sys.exit(1)


def _seed_agent(api: str, pace_ms: int) -> None:
    body = {
        "id": AGENT_ID,
        "runtime": "lab",
        "role": "smoke_pace_bot",
        "target_system": "github",
        "goal": "Read a few repos to time the pacing of a live run",
        "capability_scope": ["read_repo"],
        "principal": "smoke@acme",
        "pace_ms": pace_ms,
    }
    status, _ = _req("POST", f"{api}/config/agents", body)
    _expect(status == 201, f"seed agent -> {status}")


def _set_pace(api: str, pace_ms: int) -> None:
    status, _ = _req("PUT", f"{api}/config/agents/{AGENT_ID}", {"pace_ms": pace_ms})
    _expect(status == 200, f"set pace_ms={pace_ms} -> {status}")


def _delete_agent(api: str) -> None:
    _req("DELETE", f"{api}/config/agents/{AGENT_ID}")


def _run_once(api: str) -> tuple[float, list[dict]]:
    """Launch one lane_b run, poll to terminal, return (wall_seconds, actions)."""
    started = time.monotonic()
    status, body = _req(
        "POST",
        f"{api}/runs",
        {"kind": "lane_b", "params": {"agent_id": AGENT_ID, "stub_script": STUB_SCRIPT}},
    )
    _expect(status == 201 and isinstance(body, dict), f"launch run -> {status}")
    run_id = body["run_id"]  # type: ignore[index]
    deadline = started + 30
    while True:
        status, run = _req("GET", f"{api}/runs/{run_id}")
        _expect(status == 200 and isinstance(run, dict), f"poll run -> {status}")
        state = run["status"]  # type: ignore[index]
        if state in ("completed", "failed", "stopped"):
            _expect(state == "completed", f"run terminal status was {state!r}, expected completed")
            break
        _expect(time.monotonic() < deadline, "run did not reach terminal status within 30s")
        time.sleep(0.05)
    elapsed = time.monotonic() - started
    # Pull the emitted frames; collect the action of each "step" frame.
    status, events = _req("GET", f"{api}/runs/{run_id}/events")
    _expect(status == 200 and isinstance(events, list), f"get events -> {status}")
    actions: list[dict] = []
    for frame in events:  # type: ignore[union-attr]
        if frame.get("type") == "step":
            data = frame.get("data", {})
            action = data.get("action")
            if action is None and "action_type" in data:
                action = {k: data.get(k) for k in ("action_type", "resource", "mode")}
            if action is not None:
                actions.append(action)
    return elapsed, actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8090")
    args = parser.parse_args()
    api = args.api.rstrip("/")

    status, _ = _req("GET", f"{api}/health")
    _expect(status == 200, f"API health -> {status} (start it with ./recette.sh platform up)")

    _delete_agent(api)  # re-runnable
    try:
        # 1. paced run
        _seed_agent(api, PACE_MS)
        paced_s, paced_actions = _run_once(api)
        print(f"[1/3] paced run (pace_ms={PACE_MS}, {STEPS} steps): {paced_s:.3f}s")

        # 2. unpaced run (same agent, pace 0)
        _set_pace(api, 0)
        fast_s, fast_actions = _run_once(api)
        print(f"[2/3] unpaced run (pace_ms=0): {fast_s:.3f}s")

        # 3a. pacing really slowed the live run: at least half the nominal added
        # delay (STEPS sleeps of PACE_MS), tolerant of scheduling jitter.
        min_delta = (STEPS * PACE_MS / 1000.0) * 0.5
        delta = paced_s - fast_s
        _expect(
            delta >= min_delta,
            f"paced run not slower enough: delta={delta:.3f}s < min={min_delta:.3f}s",
        )
        # 3b. live I4 echo: pacing did not change the judged actions.
        _expect(
            paced_actions == fast_actions,
            f"action frames differ between paced and unpaced run:\n"
            f"  paced={json.dumps(paced_actions)}\n  fast={json.dumps(fast_actions)}",
        )
        _expect(
            len(paced_actions) == STEPS,
            f"expected {STEPS} step actions, got {len(paced_actions)}",
        )
        print(
            f"[3/3] delta={delta:.3f}s >= {min_delta:.3f}s and "
            f"{len(paced_actions)} action frames identical (live I4 echo)"
        )
    finally:
        _delete_agent(api)

    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
