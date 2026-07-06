"""Per-action passport re-attestation middleware (Control Plane, I2/I3).

The launch-time admission gate audits a passport ONCE, when a run starts. But a
passport carries an ``exp``: it can expire WHILE a run is in flight. This
middleware re-attests the acting agent's passport on EVERY submission, using the
action's captured ``timestamp`` as the clock, so a passport that lapses mid-run
is caught on the first action past its ``exp``.

Determinism (I4): the clock is ``request.timestamp`` -- a captured INPUT (ISO-8601
UTC) -- never ``datetime.now()``. Two replays of the same event stream against the
same passport/keyring produce the same veto.

Fail-safe (never fail-open): the veto reason lists only reason KINDS, never key
or signature material (R8). ``admit_agent`` is itself fail-safe (any oracle error
collapses to ``untrusted``, never ``trusted``); and if ``before`` were to raise,
``MiddlewarePipeline.run_before`` converts it to a deny. Observe mode NEVER vetoes
here -- the launch gate already recorded the observe verdict; enforce mode denies
a non-trusted passport.

I/O boundary: the passport FILE is loaded at most once per ``agent_id`` and cached
(it does not change during a run). The VERDICT is NOT cached -- it is recomputed on
every action against that action's ``timestamp``, which is exactly what lets this
middleware catch a mid-run expiry.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .admission import admit_agent, load_agent_passport

if TYPE_CHECKING:
    from .gateway import ActionOutcome, ActionRequest


class PassportAdmissionMiddleware:
    """Per-action passport re-attestation (I3). Deterministic: uses the action's
    captured timestamp as `now`, so it catches a passport expiring mid-run.
    Observe mode never vetoes here (the launch gate already audited); enforce
    mode denies a non-trusted passport."""

    def __init__(
        self,
        *,
        trust: dict[str, str],
        passport_dir: str | Path,
        enforce: bool,
        declared_for: Callable[[str], list[str] | None],
    ) -> None:
        self._trust = trust
        self._passport_dir = passport_dir
        self._enforce = enforce
        self._declared_for = declared_for
        # Per-agent_id cache of the LOADED passport (the file I/O), never the
        # verdict. Values may be ``None`` (an absent passport is a legitimate
        # loaded value -> attestation ``unsigned``), so membership -- not
        # truthiness -- distinguishes "not yet loaded" from "loaded as None".
        self._passport_cache: dict[str, dict | None] = {}

    def before(self, request: ActionRequest) -> str | None:
        # Observe mode never vetoes: the launch gate already recorded the verdict.
        if not self._enforce:
            return None
        passport = self._passport_for(request.agent_id)
        declared = self._declared_for(request.agent_id)
        # Verdict recomputed EVERY action against request.timestamp (the captured
        # clock, I4) -- never cached -- so a mid-run expiry is caught.
        verdict = admit_agent(passport, declared, self._trust, request.timestamp, enforce=True)
        if verdict.status != "trusted":
            kinds = [reason["kind"] for reason in verdict.reasons]
            return f"untrusted_passport: {verdict.status} {kinds}"
        return None

    def after(self, request: ActionRequest, outcome: ActionOutcome) -> None:
        return None

    def _passport_for(self, agent_id: str) -> dict | None:
        """Load ``<passport_dir>/<agent_id>.json`` at most once per agent_id.

        The file cannot change during a run, so the loaded passport is cached. The
        VERDICT is never cached here -- ``before`` recomputes it per action so
        expiry is evaluated against each action's captured timestamp.
        """
        if agent_id not in self._passport_cache:
            self._passport_cache[agent_id] = load_agent_passport(agent_id, self._passport_dir)
        return self._passport_cache[agent_id]
