"""Canonical action event model for the recette corpus.

Mirrors a subset of the platform's AgentActionEvent (see
.claude/rules/canonical-event-model.md). Kept deterministic on purpose: no
SystemTime, no random -- event ids are a sequence and timestamps come from an
injected logical clock, so a scenario replays byte-identically (invariant I4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TargetSystem(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"


class ActionType(str, Enum):
    READ_REPO = "read_repo"
    LIST_REPOS = "list_repos"
    OPEN_ISSUE = "open_issue"
    COMMENT_ISSUE = "comment_issue"
    OPEN_PR = "open_pr"
    MERGE_PR = "merge_pr"
    PUSH = "push"
    MANAGE_WEBHOOK = "manage_webhook"
    MANAGE_RELEASE = "manage_release"
    READ_CI = "read_ci"
    TRIGGER_CI = "trigger_ci"


class Mode(str, Enum):
    READ = "read"
    WRITE = "write"


# Read-only actions; everything else is a write.
_READ_ACTIONS: frozenset[ActionType] = frozenset(
    {ActionType.READ_REPO, ActionType.LIST_REPOS, ActionType.READ_CI}
)

# Write actions that require an explicit approval before execution (invariant I6).
# A merge, a push, a webhook/release change or a CI trigger are high blast-radius.
ESCALATE_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.MERGE_PR,
        ActionType.PUSH,
        ActionType.MANAGE_WEBHOOK,
        ActionType.MANAGE_RELEASE,
        ActionType.TRIGGER_CI,
    }
)


def action_mode(action: ActionType) -> Mode:
    """Return the read/write mode implied by an action type."""
    return Mode.READ if action in _READ_ACTIONS else Mode.WRITE


class LogicalClock:
    """Deterministic monotonic clock. No wall-clock, so replays are stable (I4)."""

    def __init__(self, *, epoch: int = 1_700_000_000, step_seconds: int = 1) -> None:
        self._t = epoch
        self._step = step_seconds

    def tick(self) -> str:
        ts = self._t
        self._t += self._step
        # Logical ISO-8601 UTC stamp derived from the counter, not the host clock.
        import datetime as _dt

        return (
            _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )


@dataclass(frozen=True)
class AgentAction:
    """One recorded action performed by a test agent against a forge."""

    event_id: str
    seq: int
    timestamp: str
    agent_id: str
    principal: str  # identity actually used (may differ from the declared one)
    target_system: str
    action_type: str
    mode: str
    resource: str  # repo path, e.g. "acme/widgets"
    approved: bool = False  # whether an approval was obtained before execution (I6)
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "seq": self.seq,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "principal": self.principal,
            "target_system": self.target_system,
            "action_type": self.action_type,
            "mode": self.mode,
            "resource": self.resource,
            "approved": self.approved,
            "params": self.params,
        }
