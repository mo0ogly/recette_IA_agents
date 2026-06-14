"""Governed execution platform (Phase 1, Python).

Implements the Control/Data/Audit plane seams for sensitive agent actions:
catalog (what actions exist), policy (allow/deny/escalate), approvals (I6),
event store (I1/I4 audit log), proxy (I5 mediated side effects) and the
gateway that wires them together.

Failure mode of every component is fail-safe: unknown input, missing rule or
internal error resolves to DENY, never to execution (see failure-modes.md).
"""
