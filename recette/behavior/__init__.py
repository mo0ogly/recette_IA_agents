"""Behavioral-analysis engine: tunable, replayable analysis *waves* over frozen
agent *evidence*.

A wave is a pure function of ``(EvidenceBundle, AnalysisProfile)`` -> ``AnalysisReport``
(I4): same inputs produce a byte-identical report, so a researcher replays an
experiment and reproduces it exactly. The profile exposes four knobs -- active
``lenses``, per-lens ``thresholds``, the ``cohort`` selector, and a ``threat``
hypothesis that reweights the lenses -- so the same evidence can be analyzed under
many angles without re-capturing.

Design: docs/plans/2026-06-25-behavioral-analysis-engine-design.md
"""

from __future__ import annotations

from .evidence import EvidenceBundle, build_endpoint_inputs
from .profile import THREAT_WEIGHTS, AnalysisProfile
from .report import AgentReport, AnalysisReport, Finding

__all__ = [
    "EvidenceBundle",
    "build_endpoint_inputs",
    "AnalysisProfile",
    "THREAT_WEIGHTS",
    "AnalysisReport",
    "AgentReport",
    "Finding",
]
