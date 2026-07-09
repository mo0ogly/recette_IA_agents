"""Deterministic scenario friction -- transient tool errors that force retries.

A frictionless agent<->server exchange is short: ask, answer, done. Friction
makes the conversation NEGOTIATED and therefore observable (legibility-first):
the server transiently fails an action, the model must read the error, decide,
and retry -- producing a longer decide->act trace for the recette team and a
richer wire ground truth for discovery.

Configured per agent (R5 config-first), next to ``pace_ms``::

    "friction": {
        "transient_errors": [
            {"action_type": "open_pr", "resource": "acme/x",
             "failures": 2, "message": "503 service unavailable"}
        ]
    }

``resource`` is optional (absent = match any resource); ``failures`` is how
many matching calls fail before the action succeeds (default 1); ``message``
is the error line fed back to the model (default a 503).

Determinism (I4): the output is a pure function of the CALL SEQUENCE -- an
integer counter per rule, no clock, no random, no I/O. A replay of the same
decisions reproduces the same errors byte-identically. The error text is fed
back to the model exactly like an AgentDojo tool injection (lane_b
``tool_output``), and is persisted in the recording (RecordedStep.result), so
the negotiation stays auditable.

Failure mode: a malformed friction config NEVER breaks a run -- malformed
entries are ignored (the action just succeeds), matching the fail-safe
convention of ``resolve_pace``.
"""

from __future__ import annotations

from collections.abc import Callable

from .events import AgentAction
from .lane_b import default_tool_output

# Hard ceiling on configured failures per rule: friction must lengthen a
# conversation, never wedge it into an all-error run (max_steps still bounds
# the loop regardless).
MAX_FAILURES = 8

DEFAULT_MESSAGE = "503 service unavailable"


def _coerce_rules(friction_cfg: object) -> list[tuple[str, str | None, int, str]]:
    """Normalise the friction config into (action_type, resource, failures,
    message) rules, dropping malformed entries (fail-safe: bad config means no
    friction, never a crash)."""
    if not isinstance(friction_cfg, dict):
        return []
    entries = friction_cfg.get("transient_errors")
    if not isinstance(entries, list):
        return []
    rules: list[tuple[str, str | None, int, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        action_type = entry.get("action_type")
        if not isinstance(action_type, str) or not action_type:
            continue
        resource = entry.get("resource")
        if not isinstance(resource, str) or not resource:
            resource = None
        failures = entry.get("failures", 1)
        if isinstance(failures, bool) or not isinstance(failures, int) or failures < 1:
            failures = 1
        failures = min(failures, MAX_FAILURES)
        message = entry.get("message")
        if not isinstance(message, str) or not message:
            message = DEFAULT_MESSAGE
        rules.append((action_type, resource, failures, message))
    return rules


def friction_tool_output(
    friction_cfg: object,
    default: Callable[[AgentAction], str] = default_tool_output,
) -> Callable[[AgentAction], str]:
    """Build a lane_b ``tool_output`` that transiently fails configured actions.

    The first ``failures`` calls matching a rule return an ``error:`` line
    inviting a retry; later calls fall through to ``default``. With no valid
    rules the default is returned unwrapped (zero behaviour change).
    """
    rules = _coerce_rules(friction_cfg)
    if not rules:
        return default
    counts = [0] * len(rules)

    def tool_output(action: AgentAction) -> str:
        for i, (action_type, resource, failures, message) in enumerate(rules):
            if action.action_type != action_type:
                continue
            if resource is not None and action.resource != resource:
                continue
            if counts[i] >= failures:
                continue
            counts[i] += 1
            return (
                f"error: {message} ({action.action_type} on {action.resource}, "
                f"attempt {counts[i]}/{failures}) -- transient, retry the same action"
            )
        return default(action)

    return tool_output
