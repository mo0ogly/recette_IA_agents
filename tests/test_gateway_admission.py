"""Task 4 (integration): Gateway + PassportAdmissionMiddleware end-to-end.

Builds a real Gateway (real catalog, baseline policy, in-memory event store,
recording proxy) WITH a MiddlewarePipeline carrying the passport middleware, and
drives it through `submit`:

- enforce + absent/untrusted passport -> the submission is DENIED by the
  middleware BEFORE policy, an ACTION_DENIED event is recorded carrying the
  `untrusted_passport` reason, and the proxy is never called (I2/I6 fail-safe).
- observe -> the passport middleware never vetoes; the normal policy decides
  (here: escalate), proving the gate is observe-only.
- trusted corpus passport (gh-pr-bot, in-date, declared within scope) -> not
  vetoed by the passport gate; submission proceeds to policy (escalate).

Determinism (I4): the injected `timestamp` on each request is the clock; no wall
clock is read.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from recette.platform.catalog import load_catalog
from recette.platform.events import EventKind, PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.gateway import ActionRequest, AgentResolver, Gateway
from recette.platform.ids import SequenceIdGenerator
from recette.platform.middleware import MiddlewarePipeline
from recette.platform.passport_middleware import PassportAdmissionMiddleware
from recette.platform.policy.model import baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRUST_PATH = _REPO_ROOT / "corpus" / "keys" / "test-authority.trust.json"
_PRBOT_PASSPORT = (
    _REPO_ROOT / "corpus" / "repos" / "gh-pr-bot" / "repo" / ".inspect_ia_agents" / "passport.json"
)

#: Before gh-pr-bot's exp (2030-01-01), so the trusted case is in-date.
_NOW = "2029-01-01T00:00:00Z"

#: Config agents (for the resolver). A tool_operator invoking a governed tool on
#: mcp escalates under the baseline policy -- the signal that a submission reached
#: the policy engine (i.e. the passport gate did not veto).
AGENTS = {
    "pr-bot": {"id": "pr-bot", "role": "tool_operator", "capability_scope": ["mcp"]},
    "ghost": {"id": "ghost", "role": "tool_operator", "capability_scope": ["mcp"]},
}


class _RecordingProxy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, event):  # type: ignore[no-untyped-def]
        self.calls.append(f"{event.target_system}/{event.action_type}")
        response = {"ok": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


def _invoke(agent_id: str) -> ActionRequest:
    return ActionRequest(
        agent_id=agent_id,
        action_type="invoke_tool",
        target_system="mcp",
        resource="mcp/server",
        payload={"tool": "x"},
        timestamp=_NOW,
    )


class _Harness:
    def __init__(self, *, enforce: bool, declared_for) -> None:  # type: ignore[no-untyped-def]
        self._tmp = tempfile.TemporaryDirectory()
        self.passport_dir = Path(self._tmp.name)
        catalog = load_catalog()
        pol_tmp = tempfile.TemporaryDirectory()
        self._pol_tmp = pol_tmp
        store = PolicyStore(Path(pol_tmp.name))
        store.publish(baseline_from_catalog(catalog, version="v-test"))
        self.events = InMemoryEventStore()
        self.proxy = _RecordingProxy()
        trust = json.loads(_TRUST_PATH.read_text(encoding="utf-8"))
        middleware = PassportAdmissionMiddleware(
            trust=trust,
            passport_dir=self.passport_dir,
            enforce=enforce,
            declared_for=declared_for,
        )
        self.gateway = Gateway(
            catalog=catalog,
            policy_store=store,
            event_store=self.events,
            proxy=self.proxy,
            id_generator=SequenceIdGenerator(),
            agent_resolver=AgentResolver(lambda a: AGENTS.get(a)),
            middleware=MiddlewarePipeline([middleware]),
        )

    def place_passport(self, agent_id: str, source: Path) -> None:
        shutil.copyfile(source, self.passport_dir / f"{agent_id}.json")

    def denied_reasons(self) -> list[str]:
        out: list[str] = []
        for ev in self.events.read_from(kind=EventKind.ACTION_DENIED):
            reason = ev.payload.get("extra", {}).get("deny_reason")
            if reason is not None:
                out.append(str(reason))
        return out

    def close(self) -> None:
        self._tmp.cleanup()
        self._pol_tmp.cleanup()


class GatewayAdmissionTest(unittest.TestCase):
    def test_enforce_absent_passport_is_denied_by_middleware(self) -> None:
        # No passport file for "ghost" -> unsigned -> untrusted in enforce.
        h = _Harness(enforce=True, declared_for=lambda _aid: ["read_repo"])
        try:
            outcome = h.gateway.submit(_invoke("ghost"))
            self.assertEqual(outcome.verdict, PolicyVerdict.DENY)
            self.assertEqual(h.proxy.calls, [])  # never executed (fail-safe)
            self.assertIsNotNone(outcome.error)
            self.assertIn("untrusted_passport", outcome.error or "")
            denied = h.denied_reasons()
            self.assertEqual(len(denied), 1)
            self.assertIn("untrusted_passport", denied[0])
        finally:
            h.close()

    def test_observe_passport_never_vetoes_policy_decides(self) -> None:
        # Observe mode: even with no passport, the passport gate does not veto;
        # the baseline policy escalates the governed tool call.
        h = _Harness(enforce=False, declared_for=lambda _aid: ["read_repo"])
        try:
            outcome = h.gateway.submit(_invoke("ghost"))
            self.assertEqual(outcome.verdict, PolicyVerdict.ESCALATE)
            self.assertEqual(h.denied_reasons(), [])
        finally:
            h.close()

    def test_enforce_trusted_passport_proceeds_to_policy(self) -> None:
        # gh-pr-bot trusted passport; declared within its signed scope -> no veto.
        prbot_scope = list(json.loads(_PRBOT_PASSPORT.read_text(encoding="utf-8"))["scope"])
        h = _Harness(enforce=True, declared_for=lambda _aid: prbot_scope)
        try:
            h.place_passport("pr-bot", _PRBOT_PASSPORT)
            outcome = h.gateway.submit(_invoke("pr-bot"))
            # Passport gate passed -> policy reached the governed tool -> escalate.
            self.assertEqual(outcome.verdict, PolicyVerdict.ESCALATE)
            self.assertNotIn("untrusted_passport", outcome.error or "")
            self.assertEqual(h.denied_reasons(), [])
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
