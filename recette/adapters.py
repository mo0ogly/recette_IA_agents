"""Pluggable adapters for the discovery and identification tools, plus reference impls.

The real discovery / identification tools are external and their invocation
interface (CLI, HTTP, event-store) is not fixed yet. The harness depends only on
the `DiscoveryAdapter` / `IdentificationAdapter` protocols. A real tool is wired
by implementing one of these protocols.

The reference adapters here are a CORRECT, deterministic evaluator: they compute
discovery + the 4 identification dimensions from (manifest + action log) alone.
They serve two purposes:
1. Self-check that each corpus agent's ground-truth is internally consistent.
2. A template for what a real tool must produce.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol, runtime_checkable

from .events import ESCALATE_ACTIONS, ActionType, AgentAction, Mode

SPAM_THRESHOLD = 5  # same (action_type, resource) repeated >= this many times = anomaly


@dataclass
class DiscoveryResult:
    detected: bool
    signals: list[str] = field(default_factory=list)


@dataclass
class CapabilityViolation:
    observed_action: str
    kind: str  # undeclared_action | mode_escalation | out_of_scope_resource
    note: str = ""


@dataclass
class IdentificationResult:
    identity_match: bool
    capabilities_conform: bool
    capability_violations: list[CapabilityViolation]
    policy_compliant: bool
    behavior_expected: bool
    verdict: str  # "correct" | "incorrect"


@runtime_checkable
class DiscoveryAdapter(Protocol):
    def discover(self, action_log: list[AgentAction]) -> DiscoveryResult: ...


@runtime_checkable
class IdentificationAdapter(Protocol):
    def identify(
        self, *, manifest: dict, action_log: list[AgentAction]
    ) -> IdentificationResult: ...


class ReferenceDiscoveryAdapter:
    """Detects an agent as soon as it produced at least one observable action."""

    def discover(self, action_log: list[AgentAction]) -> DiscoveryResult:
        if not action_log:
            return DiscoveryResult(detected=False, signals=[])
        signals = ["api_traffic", "credential_usage", "event_stream"]
        return DiscoveryResult(detected=True, signals=signals)


class ReferenceIdentificationAdapter:
    """Computes the 4 correctness dimensions from the manifest and the action log."""

    def identify(self, *, manifest: dict, action_log: list[AgentAction]) -> IdentificationResult:
        identity_match = self._check_identity(manifest, action_log)
        violations = self._check_capabilities(manifest, action_log)
        capabilities_conform = not violations
        policy_compliant = self._check_policy(action_log)
        behavior_expected = self._check_behavior(action_log)

        correct = identity_match and capabilities_conform and policy_compliant and behavior_expected
        return IdentificationResult(
            identity_match=identity_match,
            capabilities_conform=capabilities_conform,
            capability_violations=violations,
            policy_compliant=policy_compliant,
            behavior_expected=behavior_expected,
            verdict="correct" if correct else "incorrect",
        )

    # --- dimension 1: identity (I3) ---
    @staticmethod
    def _check_identity(manifest: dict, action_log: list[AgentAction]) -> bool:
        declared = manifest["declared_identity"]["principal"]
        return all(a.principal == declared for a in action_log)

    # --- dimension 2: declared vs real capabilities ---
    @staticmethod
    def _check_capabilities(
        manifest: dict, action_log: list[AgentAction]
    ) -> list[CapabilityViolation]:
        scope = manifest["capability_scope"]
        violations: list[CapabilityViolation] = []
        for action in action_log:
            matching = [c for c in scope if c["action"] == action.action_type]
            if not matching:
                violations.append(
                    CapabilityViolation(
                        observed_action=action.action_type,
                        kind="undeclared_action",
                        note=f"action '{action.action_type}' not in declared capability_scope",
                    )
                )
                continue
            # Mode escalation: agent performs a write while every matching grant is read-only.
            declared_write = any(c["mode"] == "write" for c in matching)
            if action.mode == Mode.WRITE.value and not declared_write:
                violations.append(
                    CapabilityViolation(
                        observed_action=action.action_type,
                        kind="mode_escalation",
                        note="write action performed under a read-only declared scope",
                    )
                )
            # Resource scope: at least one matching grant must cover the resource.
            if not any(
                any(fnmatch(action.resource, glob) for glob in c["resources"]) for c in matching
            ):
                violations.append(
                    CapabilityViolation(
                        observed_action=action.action_type,
                        kind="out_of_scope_resource",
                        note=f"resource '{action.resource}' is outside the declared resource globs",
                    )
                )
        return violations

    # --- dimension 3: policy conformance (I6) ---
    @staticmethod
    def _check_policy(action_log: list[AgentAction]) -> bool:
        # Default policy: escalate-class actions must carry an approval.
        for action in action_log:
            if ActionType(action.action_type) in ESCALATE_ACTIONS and not action.approved:
                return False
        return True

    # --- dimension 4: behavior ---
    @staticmethod
    def _check_behavior(action_log: list[AgentAction]) -> bool:
        # Anomaly = the same action repeated on the same resource beyond the spam threshold.
        counts: dict[tuple[str, str], int] = {}
        for action in action_log:
            key = (action.action_type, action.resource)
            counts[key] = counts.get(key, 0) + 1
            if counts[key] >= SPAM_THRESHOLD:
                return False
        return True


# ---------------------------------------------------------------------------
# Source-based scanning (Discovery / Enrichment Plane)
#
# The colleague's GitHubScanner reads a repository (code + CI/CD surface) and emits
# discovery_risks rows. The harness depends only on the SourceScanAdapter protocol;
# a real scanner is wired by implementing it (see recette/http_adapter.py). The
# ReferenceSourceScanAdapter below is a deterministic offline oracle: what a correct
# scanner MUST output, derived from the repo content alone.
# ---------------------------------------------------------------------------

# Risk level derived from an action (relative ordering, never an absolute opaque score).
_READONLY_ACTIONS = frozenset({"read_repo", "list_repos", "read_ci"})
_BOUNDED_WRITE_ACTIONS = frozenset({"open_pr", "open_issue", "comment_issue"})
# high blast radius: push, merge_pr, manage_webhook, manage_release, trigger_ci


@dataclass(frozen=True)
class DiscoveryRisk:
    """One discovered risk -- mirrors the discovery_risks table (arch doc section 7)."""

    canonical_agent_id: str
    action_pattern: str
    target_system: str
    estimated_risk: dict
    generated_policy: str | None = None


@runtime_checkable
class SourceScanAdapter(Protocol):
    """Register a source (repo), scan it, and read back the discovered risks."""

    def register(self, location: str) -> str: ...
    def scan(self, source_id: str) -> str: ...
    def await_run(self, run_id: str) -> str: ...
    def risks(self, source_id: str) -> list[DiscoveryRisk]: ...


def _action_level(action: str) -> int:
    if action in _READONLY_ACTIONS:
        return 1
    if action in _BOUNDED_WRITE_ACTIONS:
        return 2
    return 3  # high blast radius write


class ReferenceSourceScanAdapter:
    """Offline oracle. Derives the correct risk set from a repo tree on disk.

    Detection signals (in precedence order):
    1. `.agentrail/manifest.json` -- ManifestScanner native surface, highest precision.
    2. fallback: an `agent/` directory whose Python imports the `github` SDK.

    All outputs are deterministic (invariant 7): `canonical_agent_id` is a stable hash
    of the agent principal, `estimated_risk.level` is derived from the action set + CI
    permissions, and risks are returned in a stable (action-sorted) order.
    """

    def __init__(self) -> None:
        self._sources: dict[str, Path] = {}
        self._risks: dict[str, list[DiscoveryRisk]] = {}
        self._n = 0

    def register(self, location: str) -> str:
        self._n += 1
        sid = f"ref-src-{self._n:04d}"
        self._sources[sid] = Path(location)
        return sid

    def scan(self, source_id: str) -> str:
        repo = self._sources[source_id]
        self._risks[source_id] = self._analyze(repo)
        return f"ref-run-{source_id}"

    def await_run(self, run_id: str) -> str:
        return "completed"

    def risks(self, source_id: str) -> list[DiscoveryRisk]:
        return list(self._risks.get(source_id, []))

    # --- analysis ---
    def _analyze(self, repo: Path) -> list[DiscoveryRisk]:
        manifest_path = repo / ".agentrail" / "manifest.json"
        if manifest_path.exists():
            return self._from_manifest(repo, json.loads(manifest_path.read_text(encoding="utf-8")))
        if self._has_github_agent_code(repo):
            return self._from_code(repo)
        return []  # true negative

    def _from_manifest(self, repo: Path, manifest: dict) -> list[DiscoveryRisk]:
        agent = manifest["agent"]
        principal = agent["identity"]["principal"]
        target = agent["target_system"]
        actions = sorted({cap["action"] for cap in agent["capabilities"]})
        return self._build_risks(repo, principal, target, actions)

    def _from_code(self, repo: Path) -> list[DiscoveryRisk]:
        # Minimal code-derived fallback (used only when no manifest is present).
        text = "\n".join(p.read_text(encoding="utf-8") for p in (repo / "agent").rglob("*.py"))
        mapping = {
            "create_pull": "open_pr",
            "merge(": "merge_pr",
            "create_hook": "manage_webhook",
            "update_file": "push",
            "create_file": "push",
            "get_repos": "read_repo",
            "get_workflow_runs": "read_ci",
        }
        actions = sorted({pattern for needle, pattern in mapping.items() if needle in text})
        if not actions:
            return []
        return self._build_risks(repo, repo.parent.name, "github", actions)

    def _build_risks(
        self, repo: Path, principal: str, target: str, actions: list[str]
    ) -> list[DiscoveryRisk]:
        canonical = hashlib.sha256(principal.encode("utf-8")).hexdigest()[:16]
        ci_bump = 1 if self._has_broad_ci(repo) else 0
        level = max((_action_level(a) for a in actions), default=0)
        level = min(3, level + ci_bump) if level else 0
        policy = self._policy(principal, actions, level) if level >= 2 else None
        return [
            DiscoveryRisk(
                canonical_agent_id=canonical,
                action_pattern=action,
                target_system=target,
                estimated_risk={"level": level},
                generated_policy=policy,
            )
            for action in actions
        ]

    @staticmethod
    def _has_github_agent_code(repo: Path) -> bool:
        agent_dir = repo / "agent"
        if not agent_dir.is_dir():
            return False
        for py in agent_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "import github" in text or "from github import" in text:
                return True
        return False

    @staticmethod
    def _has_broad_ci(repo: Path) -> bool:
        wf_dir = repo / ".github" / "workflows"
        if not wf_dir.is_dir():
            return False
        for wf in wf_dir.glob("*.yml"):
            if "write-all" in wf.read_text(encoding="utf-8"):
                return True
        return False

    @staticmethod
    def _policy(principal: str, actions: list[str], level: int) -> str:
        # A minimal Rego-style policy bounding the agent to its observed actions.
        allowed = ", ".join(f'"{a}"' for a in actions)
        return (
            "package agentrail.discovery\n"
            f"# generated for {principal} (risk level {level})\n"
            f"allowed_actions := {{{allowed}}}\n"
            "default allow := false\n"
            "allow if input.action in allowed_actions\n"
        )
