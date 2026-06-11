"""AgentRail recette: ground-truth corpus + validation harness for the discovery
and identification tools.

This is the recette side of Railgun/AgentRail. It produces deterministic test
agents (GitHub/GitLab) and scores the tools against per-agent ground-truth.
"""

from __future__ import annotations

from .adapters import (
    DiscoveryAdapter,
    DiscoveryResult,
    DiscoveryRisk,
    IdentificationAdapter,
    IdentificationResult,
    ReferenceDiscoveryAdapter,
    ReferenceIdentificationAdapter,
    ReferenceSourceScanAdapter,
    SourceScanAdapter,
)
from .agent import TestAgent
from .events import ActionType, AgentAction, TargetSystem
from .forge import GitForge, LabForge, RealForge
from .harness import run_agent, run_recette
from .scorecard import AgentResult, Scorecard

__all__ = [
    "ActionType",
    "AgentAction",
    "AgentResult",
    "DiscoveryAdapter",
    "DiscoveryResult",
    "DiscoveryRisk",
    "GitForge",
    "IdentificationAdapter",
    "IdentificationResult",
    "LabForge",
    "RealForge",
    "ReferenceDiscoveryAdapter",
    "ReferenceIdentificationAdapter",
    "ReferenceSourceScanAdapter",
    "Scorecard",
    "SourceScanAdapter",
    "TargetSystem",
    "TestAgent",
    "run_agent",
    "run_recette",
]
