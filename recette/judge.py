"""Unified identification entrypoint over the merged agent model.

After the git/MAF fusion a subject is one manifest with a ``kind`` discriminator
(git_agent | maf_agent). ``judge_subject`` is the single judge the harness,
report and API call: it routes a subject to the family-appropriate four-dimension
evaluator and returns the same IdentificationResult either way.

The two families keep distinct action-log shapes (git: AgentAction with
principal/resource/mode; MAF: MafAction with provider/tool_kind/approval) -- the
dimensions are computed differently, but the verdict contract is identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .adapters import IdentificationResult, ReferenceIdentificationAdapter
from .maf_judge import MafAction, judge_maf

if TYPE_CHECKING:
    from .events import AgentAction


def subject_family(manifest: dict) -> str:
    """Return the subject family, defaulting to git_agent for backward compatibility."""
    return manifest.get("kind", "git_agent")


def judge_subject(
    manifest: dict, action_log: list[AgentAction] | list[MafAction]
) -> IdentificationResult:
    """Render the four-dimension verdict for any subject family.

    ``action_log`` must match the manifest family: AgentAction for git_agent,
    MafAction for maf_agent.
    """
    if subject_family(manifest) == "maf_agent":
        return judge_maf(manifest, action_log)  # type: ignore[arg-type]
    return ReferenceIdentificationAdapter().identify(
        manifest=manifest,
        action_log=action_log,  # type: ignore[arg-type]
    )
