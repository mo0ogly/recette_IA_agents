"""Canonical action event model for the recette corpus.

Mirrors a subset of the platform's AgentActionEvent (see
.claude/rules/canonical-event-model.md). Kept deterministic on purpose: no
SystemTime, no random -- event ids are a sequence and timestamps come from an
injected logical clock, so a scenario replays byte-identically (invariant I4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TargetSystem(StrEnum):
    GITHUB = "github"
    GITLAB = "gitlab"
    TEMPORAL = "temporal"


class ActionType(StrEnum):
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


class Mode(StrEnum):
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
    """Return the read/write mode implied by a canonical git action type."""
    return Mode.READ if action in _READ_ACTIONS else Mode.WRITE


def scenario_action_entry(
    *, action: str, resource: str, approved: bool = False, params: dict | None = None
) -> dict:
    """Build one ``scenario.json`` action entry (corpus/schemas/scenario.schema.json).

    The single source of truth for the on-disk shape of a scenario action step,
    shared by the promote path (which reads recording dicts) and the red-team
    freezer (which reads typed ``AgentAction`` objects). The entry always carries
    ``action`` + ``resource``; the optional ``approved`` flag (I6) and ``params``
    are included ONLY when truthy, so the JSON stays minimal and byte-stable. The
    principal lives once at the scenario level (``credential_principal``), never
    on the per-action entry.
    """
    entry: dict = {"action": action, "resource": resource}
    if approved:
        entry["approved"] = True
    if params:
        entry["params"] = params
    return entry


# Read-only verbs for the broader multi-system action catalog (okta, finance,
# slack, ...). A read does not mutate the target; an export reads/exfiltrates,
# so it is classified read (no mutation), independently of its risk level.
_READ_PREFIXES: tuple[str, ...] = (
    "read_",
    "list_",
    "get_",
    "view_",
    "fetch_",
    "scan_",
    "describe_",
    "export_",
    "search_",
    "download_",
)


def mode_for_action(action_type: str) -> Mode:
    """Read/write mode for ANY action type. Uses the canonical git mapping when
    the action is a known git action, else a read-prefix heuristic. Never raises
    (unlike ``action_mode`` which requires an ``ActionType`` member)."""
    try:
        return action_mode(ActionType(action_type))
    except ValueError:
        return Mode.READ if action_type.startswith(_READ_PREFIXES) else Mode.WRITE


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
            _dt.datetime.fromtimestamp(ts, tz=_dt.UTC)
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

    @classmethod
    def from_dict(cls, data: dict) -> AgentAction:
        """Rebuild an AgentAction from its ``to_dict`` form (e.g. a run's result
        frame), tolerating missing optional fields."""
        return cls(
            event_id=data["event_id"],
            seq=data["seq"],
            timestamp=data["timestamp"],
            agent_id=data["agent_id"],
            principal=data["principal"],
            target_system=data["target_system"],
            action_type=data["action_type"],
            mode=data["mode"],
            resource=data["resource"],
            approved=data.get("approved", False),
            params=dict(data.get("params", {})),
        )
