"""I4: same request stream + same policy version => byte-identical event log.

Template from .claude/rules/determinism-replay.md: replay a known stream twice
and against a committed golden. Any nondeterminism (clock, random, dict order)
in the decision path breaks this test.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.platform.catalog import Catalog
from recette.platform.catalog.model import ActionSpec, RiskLevel
from recette.platform.events import PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.gateway import ActionRequest, AgentResolver, Gateway
from recette.platform.ids import SequenceIdGenerator
from recette.platform.policy.model import baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

FIXTURES = Path(__file__).parent / "fixtures" / "platform"
STREAM = FIXTURES / "known_stream.jsonl"
GOLDEN = FIXTURES / "known_stream.golden.json"

SPECS = (
    ActionSpec(
        target_system="okta",
        action_type="suspend_user",
        risk_level=RiskLevel.HIGH,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="Suspend an Okta user",
    ),
    ActionSpec(
        target_system="okta",
        action_type="list_users",
        risk_level=RiskLevel.LOW,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="List users",
    ),
    ActionSpec(
        target_system="data_platform",
        action_type="delete_logs",
        risk_level=RiskLevel.CRITICAL,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description="Delete logs",
    ),
)

AGENTS = {
    "agent-admin": {"id": "agent-admin", "role": "identity_admin", "capability_scope": ["okta"]},
    "agent-bot": {"id": "agent-bot", "role": "marketing_bot", "capability_scope": []},
}


class DeterministicProxy:
    def execute(self, event) -> ExecutionResult:  # type: ignore[no-untyped-def]
        response = {"done": True, "action": event.action_type}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


def replay(stream_lines: list[dict], policies_dir: Path) -> list[dict]:
    """Run the full stream through a fresh gateway; return the event log as dicts."""
    catalog = Catalog(SPECS)
    policy_store = PolicyStore(policies_dir)
    if not policy_store.list_versions():
        policy_store.publish(baseline_from_catalog(catalog, version="v-replay"))
    events = InMemoryEventStore()
    gateway = Gateway(
        catalog=catalog,
        policy_store=policy_store,
        event_store=events,
        proxy=DeterministicProxy(),
        id_generator=SequenceIdGenerator(),
        agent_resolver=AgentResolver(lambda agent_id: AGENTS.get(agent_id)),
    )
    for line in stream_lines:
        if line["op"] == "submit":
            gateway.submit(ActionRequest(**line["request"]))
        elif line["op"] == "sweep_timeouts":
            gateway.sweep_timeouts(now_iso=line["now"])
    return [e.to_dict() for e in events.read_from()]


def load_stream() -> list[dict]:
    return [json.loads(line) for line in STREAM.read_text("utf-8").splitlines() if line.strip()]


class TestPolicyReplay(unittest.TestCase):
    def test_replay_is_deterministic_and_matches_golden(self) -> None:
        stream = load_stream()
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            run_a = replay(stream, Path(tmp_a))
            run_b = replay(stream, Path(tmp_b))
        self.assertEqual(run_a, run_b)  # determinism
        golden = json.loads(GOLDEN.read_text("utf-8"))
        self.assertEqual(run_a, golden)  # expected result


if __name__ == "__main__":
    unittest.main()
