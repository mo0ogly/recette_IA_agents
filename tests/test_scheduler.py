"""G8 autonomous scheduler: the heartbeat that fires the approval sweep + buffer flush.

Determinism (I4): the tick logic (``run_once``) is a synchronous, clock-injectable
function tested without a real timer. The sweep tick is proven against a real persisted
SQLite gateway (a past-timeout pending is resolved to TIMEOUT, never executed -- I6), and
the flush tick is proven against a real degraded ``BoundedRetryBuffer`` (the backlog is
drained). The asyncio loop lifecycle (start/stop, single firing) is covered separately.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path

from recette.platform.approvals import ApprovalService
from recette.platform.catalog import Catalog
from recette.platform.catalog.model import ActionSpec, Criticality, RiskLevel
from recette.platform.events import ApprovalState, EventKind, PolicyVerdict
from recette.platform.eventstore import EventStore, SqliteEventStore
from recette.platform.gateway import ActionRequest, AgentResolver, Gateway
from recette.platform.policy.model import baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash
from recette.platform.realtime.buffer import BoundedRetryBuffer
from recette.platform.realtime.protocol import RealtimeEvent, Subscription
from recette.platform.scheduler import (
    DEFAULT_INTERVAL_SECONDS,
    InProcessScheduler,
    NullScheduler,
    ScheduledTask,
    SchedulerConfigError,
    build_scheduler_from_env,
)

SPECS = (
    ActionSpec(
        target_system="okta",
        action_type="suspend_user",
        risk_level=RiskLevel.HIGH,
        criticality=Criticality.C2,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("identity_admin",),
        description="Suspend an Okta user",
    ),
)
AGENTS = {
    "agent-admin": {"id": "agent-admin", "role": "identity_admin", "capability_scope": ["okta"]},
}


class _RecordingProxy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, event) -> ExecutionResult:  # type: ignore[no-untyped-def]
        self.calls.append(f"{event.target_system}/{event.action_type}")
        response = {"done": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


class _RestartSafeIds:
    def __init__(self, store: EventStore) -> None:
        self._base = (len(store.read_from()) + 1) * 1_000_000
        self._n = 0

    def next_id(self) -> str:
        self._n += 1
        return f"EV{self._base + self._n:024d}"


class _FlakyTransport:
    """Inner transport whose publish fails until ``recovered`` is set (degrade then heal)."""

    def __init__(self) -> None:
        self.recovered = False
        self.published: list[RealtimeEvent] = []

    def publish(self, event: RealtimeEvent) -> None:
        if not self.recovered:
            raise ConnectionError("downstream unreachable")
        self.published.append(event)

    def subscribe(self) -> Subscription:  # pragma: no cover - unused in these tests
        raise NotImplementedError

    def close(self) -> None:
        return None


class TestRunOnce(unittest.TestCase):
    def test_fires_every_task_with_a_single_captured_clock(self) -> None:
        seen: list[str] = []

        def record(now_iso: str) -> int:
            seen.append(now_iso)
            return 2

        sched = InProcessScheduler(
            [ScheduledTask("a", record), ScheduledTask("b", record)],
            clock=lambda: "2026-06-14T00:00:00Z",
        )
        outcomes = sched.run_once()
        self.assertEqual(outcomes, {"a": 2, "b": 2})
        self.assertEqual(seen, ["2026-06-14T00:00:00Z", "2026-06-14T00:00:00Z"])

    def test_injected_now_overrides_clock(self) -> None:
        captured: list[str] = []
        sched = InProcessScheduler(
            [ScheduledTask("a", lambda now: captured.append(now) or 0)],
            clock=lambda: "WALL",
        )
        sched.run_once(now_iso="INJECTED")
        self.assertEqual(captured, ["INJECTED"])

    def test_a_failing_task_is_isolated_and_others_still_run(self) -> None:
        ran: list[str] = []

        def boom(now_iso: str) -> int:
            raise RuntimeError("task blew up")

        def ok(now_iso: str) -> int:
            ran.append("ok")
            return 1

        sched = InProcessScheduler(
            [ScheduledTask("boom", boom), ScheduledTask("ok", ok)],
            clock=lambda: "T",
        )
        outcomes = sched.run_once()
        self.assertEqual(outcomes, {"boom": -1, "ok": 1})
        self.assertEqual(ran, ["ok"])


class TestSweepTask(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._db = Path(self._tmp.name) / "events.db"
        self._policy_dir = Path(self._tmp.name) / "policies"
        self.catalog = Catalog(SPECS)
        PolicyStore(self._policy_dir).publish(baseline_from_catalog(self.catalog, version="v-test"))

    def _gateway(self, proxy: _RecordingProxy) -> Gateway:
        store = SqliteEventStore(self._db)
        return Gateway(
            catalog=self.catalog,
            policy_store=PolicyStore(self._policy_dir),
            event_store=store,
            proxy=proxy,
            id_generator=_RestartSafeIds(store),
            agent_resolver=AgentResolver(lambda agent_id: AGENTS.get(agent_id)),
        )

    def _escalate(self) -> str:
        outcome = self._gateway(_RecordingProxy()).submit(
            ActionRequest(
                agent_id="agent-admin",
                action_type="suspend_user",
                target_system="okta",
                resource="org/acme",
                payload={"reason": "test"},
                timestamp="2026-06-13T10:00:00Z",
            )
        )
        self.assertEqual(outcome.approval_state, ApprovalState.PENDING)
        return outcome.event_id

    def test_sweep_tick_times_out_a_pending_without_executing(self) -> None:
        pending_id = self._escalate()
        proxy = _RecordingProxy()
        gateway = self._gateway(proxy)

        def sweep(now_iso: str) -> int:
            return len(gateway.sweep_timeouts(now_iso=now_iso))

        sched = InProcessScheduler([ScheduledTask("approval-timeout-sweep", sweep)])
        outcomes = sched.run_once(now_iso="2999-01-01T00:00:00Z")

        self.assertEqual(outcomes, {"approval-timeout-sweep": 1})
        self.assertEqual(proxy.calls, [])  # never executed (I6)
        service = ApprovalService(SqliteEventStore(self._db))
        self.assertEqual(service.resolved_ids().get(pending_id), ApprovalState.TIMEOUT)
        executed = list(SqliteEventStore(self._db).read_from(kind=EventKind.ACTION_EXECUTED))
        self.assertEqual([e for e in executed if e.payload.get("agent_id") == "agent-admin"], [])


class TestFlushTask(unittest.TestCase):
    def test_flush_tick_drains_a_recovered_degraded_buffer(self) -> None:
        inner = _FlakyTransport()
        buffer = BoundedRetryBuffer(inner, capacity=8)
        buffer.publish({"event_id": "EV1"})  # downstream down -> buffered
        self.assertTrue(buffer.degraded)
        self.assertEqual(buffer.pending, 1)

        inner.recovered = True

        def flush_buffer(now_iso: str) -> int:
            return buffer.flush()

        sched = InProcessScheduler([ScheduledTask("realtime-buffer-flush", flush_buffer)])
        outcomes = sched.run_once(now_iso="T")

        self.assertEqual(outcomes, {"realtime-buffer-flush": 0})  # 0 still pending
        self.assertFalse(buffer.degraded)
        self.assertEqual([e["event_id"] for e in inner.published], ["EV1"])


class TestBuildFromEnv(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            k: os.environ.get(k)
            for k in ("INSPECT_IA_AGENTS_SCHEDULER", "INSPECT_IA_AGENTS_SCHEDULER_INTERVAL_SECONDS")
        }
        self.addCleanup(self._restore)
        for key in self._saved:
            os.environ.pop(key, None)

    def _restore(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_default_is_null_scheduler(self) -> None:
        self.assertIsInstance(build_scheduler_from_env([]), NullScheduler)

    def test_off_is_null_scheduler(self) -> None:
        os.environ["INSPECT_IA_AGENTS_SCHEDULER"] = "off"
        self.assertIsInstance(build_scheduler_from_env([]), NullScheduler)

    def test_inproc_builds_inprocess_scheduler_with_default_interval(self) -> None:
        os.environ["INSPECT_IA_AGENTS_SCHEDULER"] = "inproc"
        sched = build_scheduler_from_env([])
        self.assertIsInstance(sched, InProcessScheduler)
        self.assertEqual(sched._interval, DEFAULT_INTERVAL_SECONDS)  # type: ignore[attr-defined]

    def test_inproc_honours_interval_env(self) -> None:
        os.environ["INSPECT_IA_AGENTS_SCHEDULER"] = "inproc"
        os.environ["INSPECT_IA_AGENTS_SCHEDULER_INTERVAL_SECONDS"] = "5"
        sched = build_scheduler_from_env([])
        self.assertEqual(sched._interval, 5.0)  # type: ignore[attr-defined]

    def test_unknown_backend_is_refused(self) -> None:
        os.environ["INSPECT_IA_AGENTS_SCHEDULER"] = "cron"
        with self.assertRaises(SchedulerConfigError):
            build_scheduler_from_env([])

    def test_non_numeric_interval_is_refused(self) -> None:
        os.environ["INSPECT_IA_AGENTS_SCHEDULER"] = "inproc"
        os.environ["INSPECT_IA_AGENTS_SCHEDULER_INTERVAL_SECONDS"] = "soon"
        with self.assertRaises(SchedulerConfigError):
            build_scheduler_from_env([])

    def test_sub_floor_interval_is_refused(self) -> None:
        os.environ["INSPECT_IA_AGENTS_SCHEDULER"] = "inproc"
        os.environ["INSPECT_IA_AGENTS_SCHEDULER_INTERVAL_SECONDS"] = "0.1"
        with self.assertRaises(SchedulerConfigError):
            build_scheduler_from_env([])


class TestIntervalFloor(unittest.TestCase):
    def test_constructor_rejects_sub_floor_interval(self) -> None:
        with self.assertRaises(ValueError):
            InProcessScheduler([], interval_seconds=0.5)


class TestLoopLifecycle(unittest.TestCase):
    def test_null_scheduler_is_inert(self) -> None:
        sched = NullScheduler()
        sched.start()
        self.assertEqual(sched.run_once(), {})
        asyncio.run(sched.stop())  # no-op, must not raise

    def test_start_is_idempotent_and_stop_cancels(self) -> None:
        async def scenario() -> None:
            sched = InProcessScheduler([ScheduledTask("noop", lambda now: 0)], interval_seconds=1.0)
            sched.start()
            first = sched._task  # type: ignore[attr-defined]
            sched.start()
            self.assertIs(sched._task, first)  # type: ignore[attr-defined]
            await sched.stop()
            self.assertIsNone(sched._task)  # type: ignore[attr-defined]
            await sched.stop()  # idempotent

        asyncio.run(scenario())

    def test_heartbeat_fires_the_task_then_stops(self) -> None:
        async def scenario() -> bool:
            fired = threading.Event()

            def task(now_iso: str) -> int:
                fired.set()
                return 1

            sched = InProcessScheduler([ScheduledTask("t", task)], interval_seconds=1.0)
            sched.start()
            got = await asyncio.to_thread(fired.wait, 5.0)
            await sched.stop()
            return got

        self.assertTrue(asyncio.run(scenario()))


if __name__ == "__main__":
    unittest.main()
