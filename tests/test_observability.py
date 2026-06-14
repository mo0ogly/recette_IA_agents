"""G6 forensic correlation logging (R6): every governed event yields a structured
log record keyed by event_id so an auditor can reconstruct a flow from the logs."""

from __future__ import annotations

import io
import json
import logging
import unittest

from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.observability import (
    CORRELATION_FIELDS,
    JsonLogFormatter,
    configure_observability_from_env,
    log_correlated,
)
from recette.platform.realtime import InProcessTransport, PublishingEventStore

SCHEMA = "v1"


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class LogCorrelatedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("inspect_ia_agents.test.correlate")
        self.logger.handlers = []
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        self.cap = _Capture()
        self.logger.addHandler(self.cap)

    def test_promotes_event_id_and_agent_id_onto_record(self) -> None:
        log_correlated(self.logger, logging.INFO, "x", event_id="EV1", agent_id="a", verdict="deny")
        rec = self.cap.records[-1]
        self.assertEqual(rec.event_id, "EV1")
        self.assertEqual(rec.agent_id, "a")
        self.assertEqual(rec.verdict, "deny")

    def test_unknown_and_none_fields_are_dropped(self) -> None:
        log_correlated(
            self.logger, logging.INFO, "x", event_id="EV1", agent_id=None, bogus="z", kind=None
        )
        rec = self.cap.records[-1]
        self.assertEqual(rec.event_id, "EV1")
        self.assertFalse(hasattr(rec, "agent_id"))
        self.assertFalse(hasattr(rec, "bogus"))
        self.assertFalse(hasattr(rec, "kind"))

    def test_flow_is_reconstructable_by_event_id(self) -> None:
        log_correlated(self.logger, logging.INFO, "a", event_id="EV1", kind="action_requested")
        log_correlated(self.logger, logging.INFO, "b", event_id="EV2", kind="action_denied")
        log_correlated(
            self.logger,
            logging.INFO,
            "c",
            event_id="EV9",
            correlates_event_id="EV1",
            kind="approval_resolved",
        )
        # Filtering on the action's event_id plus anything that correlates to it
        # reconstructs the whole flow (the request + its resolution).
        flow = [
            r
            for r in self.cap.records
            if getattr(r, "event_id", None) == "EV1"
            or getattr(r, "correlates_event_id", None) == "EV1"
        ]
        self.assertEqual([r.getMessage() for r in flow], ["a", "c"])


class JsonLogFormatterTest(unittest.TestCase):
    def test_emits_valid_json_with_correlation_fields(self) -> None:
        rec = logging.LogRecord(
            "inspect_ia_agents.audit", logging.INFO, __file__, 1, "msg", None, None
        )
        rec.event_id = "EV1"
        rec.agent_id = "agent-x"
        rec.verdict = "allow"
        line = JsonLogFormatter().format(rec)
        obj = json.loads(line)
        self.assertEqual(obj["event_id"], "EV1")
        self.assertEqual(obj["agent_id"], "agent-x")
        self.assertEqual(obj["verdict"], "allow")
        self.assertEqual(obj["message"], "msg")
        self.assertEqual(obj["level"], "INFO")

    def test_omits_absent_fields(self) -> None:
        rec = logging.LogRecord(
            "inspect_ia_agents.audit", logging.INFO, __file__, 1, "msg", None, None
        )
        rec.event_id = "EV1"
        obj = json.loads(JsonLogFormatter().format(rec))
        self.assertNotIn("agent_id", obj)
        self.assertEqual(set(obj) & set(CORRELATION_FIELDS), {"event_id"})


class ConfigureFromEnvTest(unittest.TestCase):
    def _run(self, env: dict[str, str]):
        import os

        _keys = ("INSPECT_IA_AGENTS_LOG_FORMAT", "INSPECT_IA_AGENTS_LOG_LEVEL")
        saved = {k: os.environ.get(k) for k in _keys}
        os.environ.update(env)
        for k in ("INSPECT_IA_AGENTS_LOG_FORMAT", "INSPECT_IA_AGENTS_LOG_LEVEL"):
            if k not in env:
                os.environ.pop(k, None)
        try:
            stream = io.StringIO()
            logger = configure_observability_from_env(stream=stream)
            return logger, stream
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_json_format_emits_json_line(self) -> None:
        logger, stream = self._run({"INSPECT_IA_AGENTS_LOG_FORMAT": "json"})
        log_correlated(logger, logging.INFO, "hello", event_id="EV1", agent_id="a")
        obj = json.loads(stream.getvalue().strip().splitlines()[-1])
        self.assertEqual(obj["event_id"], "EV1")
        self.assertEqual(obj["message"], "hello")

    def test_text_format_is_not_json(self) -> None:
        logger, stream = self._run({"INSPECT_IA_AGENTS_LOG_FORMAT": "text"})
        log_correlated(logger, logging.INFO, "hello", event_id="EV1")
        out = stream.getvalue()
        self.assertIn("hello", out)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out.strip())

    def test_idempotent_no_handler_stacking(self) -> None:
        self._run({"INSPECT_IA_AGENTS_LOG_FORMAT": "json"})
        logger, _ = self._run({"INSPECT_IA_AGENTS_LOG_FORMAT": "json"})
        self.assertEqual(len(logger.handlers), 1)

    def test_level_from_env(self) -> None:
        logger, _ = self._run({"INSPECT_IA_AGENTS_LOG_LEVEL": "WARNING"})
        self.assertEqual(logger.level, logging.WARNING)


class PublishingStoreEmitsCorrelationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.audit = logging.getLogger("inspect_ia_agents.audit")
        self.audit.handlers = []
        self.audit.propagate = False
        self.audit.setLevel(logging.INFO)
        self.cap = _Capture()
        self.audit.addHandler(self.cap)

    def test_append_emits_correlated_audit_record(self) -> None:
        store = PublishingEventStore(InMemoryEventStore(), InProcessTransport())
        store.append(
            event_id="EV100",
            kind="action_executed",
            payload={
                "agent_id": "agent-x",
                "target_system": "okta",
                "action_type": "list_users",
                "policy_decision": {"verdict": "allow", "policy_version": "v1", "rule_id": "r1"},
            },
            schema_version=SCHEMA,
        )
        rec = next(r for r in self.cap.records if getattr(r, "event_id", None) == "EV100")
        self.assertEqual(rec.agent_id, "agent-x")
        self.assertEqual(rec.kind, "action_executed")
        self.assertEqual(rec.verdict, "allow")
        self.assertEqual(rec.target_system, "okta")


if __name__ == "__main__":
    unittest.main()
