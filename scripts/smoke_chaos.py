#!/usr/bin/env python3
"""Chaos fail-safe smoke (A1): prove the governed proxy path SURFACES an INFRA
fault instead of fabricating success.

The lab chaos layer (recette/lab/chaos.py, #5) lets a target system return
429/503/504. This smoke wires a real mock server with chaos ON for one system and
OFF for another, drives a side effect through the SAME LabHttpProxy the platform
uses (I5), and asserts the failure-modes property:

  - a faulting system (503) -> ExecutionResult.ok == False, status 503, an error
    surfaced, and NO side_effect_hash. The proxy did NOT optimistically report a
    success: there is no fabricated effect to audit (failure-modes.md, I5/I6).
  - a non-faulting system (rate 0) -> ok == True, status 200, a side_effect_hash.
    Chaos is TARGETED, not a blanket outage.

This turns #5 from "built + unit-tested" into "the fail-safe behaviour is proven
live end to end". Stdlib only, self-contained (spins its own server on a high
port), re-runnable. Exit 0 = all assertions passed, 1 = failure.

Usage: python3 scripts/smoke_chaos.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_CHAOS = json.dumps(
    {
        "seed": "smoke",
        "systems": {
            "okta": {"error_rate": 1.0, "statuses": [503]},
            "finance": {"error_rate": 0.0, "statuses": [503]},
        },
    }
)
_PORT = 9198


class SmokeFailure(AssertionError):
    """One smoke assertion failed; the message carries the evidence."""


def _event(target_system: str, action_type: str, resource: str):
    from recette.platform.events import PlatformActionEvent

    return PlatformActionEvent(
        event_id=f"smoke-{target_system}-{action_type}",
        timestamp="0",
        agent_id="smoke-chaos-bot",
        capability_scope=(action_type,),
        role="admin",
        action_type=action_type,
        target_system=target_system,
        resource=resource,
        payload={},
        risk_score=0,
        risk_level="low",
    )


def main() -> int:
    # Chaos must be set BEFORE importing the mock server (it loads the policy at
    # import). Force a fresh import in case a previous import cached it.
    os.environ["INSPECT_IA_AGENTS_LAB_CHAOS"] = _CHAOS
    for mod in ("recette.lab.mock_server",):
        sys.modules.pop(mod, None)
    import recette.lab.mock_server as ms

    if ms._CHAOS is None:  # noqa: SLF001 - smoke asserts the policy actually loaded
        print("FAIL: chaos policy did not load from INSPECT_IA_AGENTS_LAB_CHAOS")
        return 1

    handler = next(
        v for k, v in vars(ms).items() if isinstance(v, type) and v.__name__ == "_Handler"
    )
    server = ThreadingHTTPServer(("127.0.0.1", _PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from recette.platform.proxy.lab_proxy import LabHttpProxy

        proxy = LabHttpProxy(base_url=f"http://127.0.0.1:{_PORT}", timeout=5.0)

        # 1. Faulting system (okta, rate 1.0) -> ok=False, 503, no fabricated effect.
        faulted = proxy.execute(_event("okta", "suspend_user", "users/1"))
        if faulted.ok:
            raise SmokeFailure(f"okta under chaos returned ok=True (optimistic!): {faulted}")
        if faulted.status_code != 503:
            raise SmokeFailure(f"okta under chaos: expected 503, got {faulted.status_code}")
        if faulted.side_effect_hash is not None:
            raise SmokeFailure(
                f"okta under chaos has a side_effect_hash (fabricated effect!): "
                f"{faulted.side_effect_hash}"
            )
        if not faulted.error:
            raise SmokeFailure("okta under chaos surfaced no error")
        print(f"[ok] faulting okta -> ok=False status=503 no-hash error={faulted.error!r}")

        # 2. Non-faulting system (finance, rate 0) -> ok=True, 200, a real effect.
        served = proxy.execute(_event("finance", "validate_invoice", "inv/42"))
        if not served.ok:
            raise SmokeFailure(f"finance (rate 0) should serve, got ok=False: {served.error}")
        if served.status_code != 200:
            raise SmokeFailure(f"finance (rate 0): expected 200, got {served.status_code}")
        if not served.side_effect_hash:
            raise SmokeFailure("finance (rate 0) has no side_effect_hash")
        print(
            f"[ok] non-faulting finance -> ok=True status=200 hash={served.side_effect_hash[:12]}"
        )

        print("\nSMOKE PASS: governed proxy surfaces the INFRA fault, no optimistic execution.")
        return 0
    except SmokeFailure as exc:
        print(f"\nSMOKE FAIL: {exc}")
        return 1
    finally:
        server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
