"""Forge abstraction: where test agents perform GitHub/GitLab actions.

`GitForge` is the mediated interface (invariant I5 in spirit -- agents never touch
an external system directly, they go through a forge). Two implementations:

- `LabForge`  : in-memory, deterministic, zero external dependency. DEFAULT.
                Records every action into an action log used by the recette adapters.
- `RealForge` : optional, talks to real GitHub/GitLab via the SDKs. Lazily imported
                so the package works without them. Writes are disabled unless
                explicitly enabled, to avoid accidental side effects on real repos.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .events import (
    ActionType,
    AgentAction,
    LogicalClock,
    TargetSystem,
    action_mode,
    mode_for_action,
)


@runtime_checkable
class GitForge(Protocol):
    """Mediated forge: agents call execute(); the forge records the action."""

    def execute(
        self,
        *,
        agent_id: str,
        principal: str,
        target_system: str,
        action_type: str,
        resource: str,
        approved: bool = False,
        params: dict | None = None,
    ) -> AgentAction: ...

    @property
    def action_log(self) -> list[AgentAction]: ...


class LabForge:
    """In-memory deterministic forge. The default execution target for the recette."""

    def __init__(self, clock: LogicalClock | None = None) -> None:
        self._log: list[AgentAction] = []
        self._clock = clock or LogicalClock()
        self._seq = 0

    def execute(
        self,
        *,
        agent_id: str,
        principal: str,
        target_system: str,
        action_type: str,
        resource: str,
        approved: bool = False,
        params: dict | None = None,
    ) -> AgentAction:
        self._seq += 1
        action = AgentAction(
            event_id=f"evt-{self._seq:04d}",
            seq=self._seq,
            timestamp=self._clock.tick(),
            agent_id=agent_id,
            principal=principal,
            target_system=target_system,
            action_type=action_type,
            mode=mode_for_action(action_type).value,
            resource=resource,
            approved=approved,
            params=dict(params or {}),
        )
        self._log.append(action)
        return action

    @property
    def action_log(self) -> list[AgentAction]:
        return list(self._log)


class RealForge:
    """Optional forge backed by real GitHub/GitLab SDKs.

    Not exercised by the default lab recette. Lazily imports the SDKs so the
    package imports cleanly without them. Tokens come from the environment
    (never hardcoded, see .claude/rules/no-hardcoded-secrets.md). Write actions
    raise unless ``enable_writes=True`` is passed, to prevent accidental side
    effects on real repositories.
    """

    def __init__(
        self,
        target_system: str,
        *,
        token: str,
        enable_writes: bool = False,
        clock: LogicalClock | None = None,
    ) -> None:
        self._target = TargetSystem(target_system)
        self._token = token
        self._enable_writes = enable_writes
        self._log: list[AgentAction] = []
        self._clock = clock or LogicalClock()
        self._seq = 0
        self._client = self._connect()

    def _connect(self) -> object:
        if self._target is TargetSystem.GITHUB:
            try:
                from github import Github  # type: ignore
            except ImportError as exc:  # pragma: no cover - depends on optional dep
                raise RuntimeError(
                    "RealForge(github) requires PyGithub (pip install 'ia_agent-recette[real]')"
                ) from exc
            return Github(self._token)
        try:
            import gitlab  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise RuntimeError(
                "RealForge(gitlab) requires python-gitlab (pip install 'ia_agent-recette[real]')"
            ) from exc
        return gitlab.Gitlab(private_token=self._token)

    def execute(
        self,
        *,
        agent_id: str,
        principal: str,
        target_system: str,
        action_type: str,
        resource: str,
        approved: bool = False,
        params: dict | None = None,
    ) -> AgentAction:  # pragma: no cover - requires live credentials
        mode = action_mode(ActionType(action_type))
        if mode.value == "write" and not self._enable_writes:
            raise PermissionError(
                f"RealForge: write action '{action_type}' blocked (enable_writes=False)"
            )
        # The concrete SDK call per action_type is wired per deployment. The
        # recorded action log keeps the same shape as LabForge so adapters are
        # forge-agnostic. Live SDK dispatch is intentionally a deployment concern.
        self._seq += 1
        action = AgentAction(
            event_id=f"evt-{self._seq:04d}",
            seq=self._seq,
            timestamp=self._clock.tick(),
            agent_id=agent_id,
            principal=principal,
            target_system=target_system,
            action_type=action_type,
            mode=mode.value,
            resource=resource,
            approved=approved,
            params=dict(params or {}),
        )
        self._log.append(action)
        return action

    @property
    def action_log(self) -> list[AgentAction]:
        return list(self._log)
