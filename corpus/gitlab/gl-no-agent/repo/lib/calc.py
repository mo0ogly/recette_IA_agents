"""Plain utility library hosted on GitLab. NOT an agent (true-negative subject).

No AgentRail manifest, no GitLab/GitHub SDK, no target-system action -- just pure
functions. The discovery scanner must not flag it as an agent (false-positive guard).
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    return a + b


def multiply(a: int, b: int) -> int:
    return a * b
