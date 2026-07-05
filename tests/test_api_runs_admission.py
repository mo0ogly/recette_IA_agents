"""Task 3: passport admission gate on POST /runs (lane_b).

Every launch is admitted through the Control Plane gate (I2/I3) and the verdict
is ALWAYS audited (I1) -- even when enforce mode denies the launch with a 403,
the AGENT_ADMISSION event is on the log BEFORE the raise. `now` is captured at
the boundary (I4). These tests inject the passport_* config into create_app so
they never touch the real corpus keyring path or an ambient env toggle.

Requires the [api] extra (fastapi). Skipped without it.

Run:  /home/fpizzi/recette_agent/.venv/bin/python -m unittest tests.test_api_runs_admission -v
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.platform.admission import load_trust
    from recette.platform.events import EventKind
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CORPUS_PASSPORT = (
    _REPO_ROOT / "corpus" / "repos" / "gh-pr-bot" / "repo" / ".inspect_ia_agents" / "passport.json"
)
_CORPUS_TRUST = _REPO_ROOT / "corpus" / "keys" / "test-authority.trust.json"

# The passport's own scope; the seeded agent declares the SAME set so there is no
# scope_overreach in the trusted case.
_PASSPORT_SCOPE = ["read_repo", "open_pr"]

_AGENT_ID = "pr-bot-under-test"
# A one-decision mock script: the agent finishes immediately (no real key, no
# network). The launch thread is fire-and-forget; the admission audit happens
# synchronously before it starts, so the event is present when the response returns.
_STUB_SCRIPT = [{"kind": "final", "text": "done"}]


def _seed_agent(store: ConfigStore) -> None:
    store.add_agent(
        {
            "id": _AGENT_ID,
            "runtime": "lab",
            "principal": "acme-platform-team",
            "target_system": "github",
            "goal": "open dependency PRs",
            "capability_scope": _PASSPORT_SCOPE,
            "ai_mode": "mock",
        }
    )


def _admission_events(store: InMemoryEventStore) -> list:
    return store.read_from(kind=EventKind.AGENT_ADMISSION.value)


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRunAdmissionGate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.passport_dir = self.tmp / "passports"
        self.passport_dir.mkdir()
        self.config_path = self.tmp / "config.json"
        self.trust = load_trust(_CORPUS_TRUST)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _client(self, *, enforce: bool) -> tuple[TestClient, InMemoryEventStore]:
        store = ConfigStore(self.config_path)
        _seed_agent(store)
        events = InMemoryEventStore()
        app = create_app(
            config_store=store,
            event_store=events,
            passport_enforce=enforce,
            passport_dir=str(self.passport_dir),
            passport_trust=self.trust,
        )
        return TestClient(app), events

    def _launch(self, client: TestClient):
        return client.post(
            "/runs",
            json={"kind": "lane_b", "params": {"agent_id": _AGENT_ID, "stub_script": _STUB_SCRIPT}},
        )

    def _write_trusted_passport(self) -> None:
        shutil.copyfile(_CORPUS_PASSPORT, self.passport_dir / f"{_AGENT_ID}.json")

    def test_observe_no_passport_admits_unsigned_and_audits(self) -> None:
        client, events = self._client(enforce=False)
        resp = self._launch(client)
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["admission"]["status"], "unsigned")
        self.assertTrue(body["admission"]["admitted"])
        self.assertEqual(body["admission"]["mode"], "observe")
        # The verdict is on the append-only log (I1).
        admissions = _admission_events(events)
        self.assertEqual(len(admissions), 1)
        payload = admissions[0].payload
        self.assertEqual(payload["agent_id"], _AGENT_ID)
        self.assertEqual(payload["status"], "unsigned")
        self.assertTrue(payload["admitted"])
        self.assertEqual(payload["mode"], "observe")
        self.assertEqual(payload["reasons"], [])

    def test_enforce_no_passport_denies_403_but_audits_first(self) -> None:
        client, events = self._client(enforce=True)
        resp = self._launch(client)
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertIn("admission denied", resp.json()["detail"])
        # The denial itself is audited BEFORE the 403 raise (I1).
        admissions = _admission_events(events)
        self.assertEqual(len(admissions), 1)
        payload = admissions[0].payload
        self.assertEqual(payload["agent_id"], _AGENT_ID)
        self.assertEqual(payload["status"], "unsigned")
        self.assertFalse(payload["admitted"])
        self.assertEqual(payload["mode"], "enforce")

    def test_enforce_trusted_passport_admits_and_audits(self) -> None:
        self._write_trusted_passport()
        client, events = self._client(enforce=True)
        resp = self._launch(client)
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["admission"]["status"], "trusted")
        self.assertTrue(body["admission"]["admitted"])
        self.assertEqual(body["admission"]["mode"], "enforce")
        admissions = _admission_events(events)
        self.assertEqual(len(admissions), 1)
        payload = admissions[0].payload
        self.assertEqual(payload["status"], "trusted")
        self.assertTrue(payload["admitted"])
        self.assertEqual(payload["reasons"], [])

    def test_admission_event_payload_shape(self) -> None:
        client, events = self._client(enforce=False)
        self._launch(client)
        payload = _admission_events(events)[0].payload
        self.assertEqual(
            set(payload),
            {"agent_id", "status", "reasons", "mode", "admitted"},
        )
        self.assertIsInstance(payload["reasons"], list)
        self.assertIsInstance(payload["admitted"], bool)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
