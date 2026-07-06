"""Task 6: consolidated passport-admission truth table + replay determinism (I4).

This is the ONE place that reads the end-to-end admission truth as a table:
observe vs enforce X {absent, expired, trusted} passport at the LAUNCH gate
(POST /runs), plus the two ACTION-level rows (a trusted-at-launch agent whose
passport is still valid vs. one that has lapsed mid-run) through the SAME Gateway
+ PassportAdmissionMiddleware that ``create_app`` wires. It builds the app via
``create_app`` with injected ``passport_enforce`` / ``passport_dir`` /
``passport_trust`` and seeds a complete runtime agent in the config store, so it
never touches the gitignored runtime store or an ambient env toggle.

Truth table (launch = POST /runs; action = gateway.submit at a chosen timestamp).
Each row is `mode + passport@<dir>/<agent_id>.json -> launch | action`:

  Row 1  observe + absent   -> 201 unsigned, admitted True | action not vetoed (policy decides)
         REFERENCED: test_api_runs_admission.test_observe_no_passport_admits_unsigned_and_audits
         REFERENCED: test_gateway_admission.test_observe_passport_never_vetoes_policy_decides
  Row 2  observe + expired  -> 201 untrusted, admitted True | action not vetoed
         NEW: test_observe_expired_fixture_launch_admits_and_audits
  Row 3  enforce + absent   -> 403, admitted False | agent never launches
         REFERENCED: test_api_runs_admission.test_enforce_no_passport_denies_403_but_audits_first
         REFERENCED: test_gateway_admission.test_enforce_absent_passport_is_denied_by_middleware
  Row 4  enforce + expired  -> 403 untrusted{expired} | --
         NEW: test_enforce_expired_fixture_launch_denies_403_audited
  Row 5  enforce + trusted, now < exp -> 201 trusted | action passes the passport middleware
         NEW: test_enforce_trusted_fixture_admits_then_mid_run_expiry_denies
  Row 6  enforce + trusted, action ts > exp -> 201 at launch | ACTION_DENIED untrusted{expired}
         NEW: same test as Row 5 (the mid-run expiry)

Rows 1 and 3 are already asserted end-to-end by the narrower launch/middleware
suites (referenced above), so they are documented here rather than re-asserted --
no duplication (R20). Rows 2, 4, 5, 6 are the missing rows and are added below.

Mid-run-expiry fixture approach (rows 5-6): NO new fixture is issued. The
committed ``trusted-agent`` fixture carries exp = 2035-01-01. The launch gate
reads the wall clock (2026 < 2035 -> trusted -> 201), and the middleware reads
the ACTION's captured timestamp -- an INPUT we control. Submitting an action with
timestamp 2036 (> exp) makes the SAME cached passport re-attest as ``expired`` and
the middleware vetoes it. The fixture's 2035 exp already straddles the wall-clock
launch and the injected post-exp action timestamp, so a dedicated controlled-exp
passport (and the Rust ``passport issue`` build it would require) is unnecessary --
the injected action clock provides the control (I4).

Replay boundary (I4): the LAUNCH endpoint captures ``now`` from the wall clock
(``_timestamp.capture_timestamp``), so it is NOT a replay surface. The replay
assertions therefore target (a) the PRIMITIVE ``admit_agent`` with an INJECTED
``now`` -- two calls yield an equal ``AdmissionVerdict`` and a byte-identical
AGENT_ADMISSION payload (``json.dumps(sort_keys=True)``) -- and (b) two identical
observe launches of an UNSIGNED agent, whose admission payload is invariant to the
boundary clock BY CONSTRUCTION (an ``unsigned`` status does not depend on ``now``),
which is exactly why that endpoint-level check is legitimate despite the wall
clock. No wall-clock value is ever asserted.

Coverage guard: ``tests/test_coverage_guard.py`` guards the CORPUS dimensions
(D1-D8: actions/roles/domains/campaigns/red-team). Admission is a runtime
governance gate, not a corpus-coverage dimension, so it is intentionally not a
coverage-guard dimension -- this admission recette is self-contained.

Requires the [api] extra (fastapi) and the [bundle] extra (cryptography, for the
real Ed25519 verify behind the trusted fixture). Skipped without fastapi.

Run:  /home/fpizzi/recette_agent/.venv/bin/python -m unittest tests.test_admission_recette -v
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.platform.admission import AdmissionVerdict, admit_agent, load_trust
    from recette.platform.events import EventKind, PolicyVerdict
    from recette.platform.eventstore.memory_store import InMemoryEventStore
    from recette.platform.gateway import ActionRequest
    from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRUST = _REPO_ROOT / "corpus" / "keys" / "test-authority.trust.json"
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "agent_passports"
_TRUSTED_FIXTURE = _FIXTURES / "trusted-agent.json"
_EXPIRED_FIXTURE = _FIXTURES / "expired-agent.json"

#: The trusted/expired fixtures both declare scope ["read_repo", "open_pr"]; the
#: seeded agent declares the SAME set so the passport attestation sees no
#: scope_overreach (the only thing under test is expiry, not scope).
_PASSPORT_SCOPE = ["read_repo", "open_pr"]

#: A one-decision mock script: the launched agent finishes immediately (no real
#: key, no network). The launch thread is fire-and-forget; the admission audit is
#: synchronous, so the AGENT_ADMISSION event is present when the response returns.
_STUB_SCRIPT = [{"kind": "final", "text": "done"}]

#: The trusted fixture's exp is 2035-01-01. These action clocks straddle it: one
#: valid (mid-run, still trusted), one lapsed (mid-run expiry). INPUTS, never the
#: wall clock (I4).
_BEFORE_EXP = "2029-01-01T00:00:00Z"
_AFTER_EXP = "2036-01-01T00:00:00Z"


def _admission_payload(agent_id: str, verdict: AdmissionVerdict) -> dict:
    """Build the AGENT_ADMISSION payload EXACTLY as ``routers/runs.py`` does, so
    the replay assertion pins the real event shape, not a private copy."""
    return {
        "agent_id": agent_id,
        "status": verdict.status,
        "reasons": list(verdict.reasons),
        "mode": verdict.mode,
        "admitted": verdict.admitted,
    }


class _RecordingProxy:
    """An in-memory proxy so a launched run / a gateway action never touches the
    real lab over HTTP, and so a mid-run veto can be proven to skip execution."""

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


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class AdmissionRecetteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.passport_dir = self.tmp / "passports"
        self.passport_dir.mkdir()
        self.config_path = self.tmp / "config.json"
        self.trust = load_trust(_TRUST)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- harness ---------------------------------------------------------

    def _seed_agent(self, store: ConfigStore, agent_id: str) -> None:
        store.add_agent(
            {
                "id": agent_id,
                "runtime": "lab",
                "principal": "acme-platform-team",
                "target_system": "gitlab",
                "goal": "read project metadata and open MRs",
                "capability_scope": list(_PASSPORT_SCOPE),
                "ai_mode": "mock",
            }
        )

    def _app(self, *, enforce: bool, agent_id: str):
        store = ConfigStore(self.config_path)
        self._seed_agent(store, agent_id)
        events = InMemoryEventStore()
        proxy = _RecordingProxy()
        app = create_app(
            config_store=store,
            event_store=events,
            proxy=proxy,
            passport_enforce=enforce,
            passport_dir=str(self.passport_dir),
            passport_trust=self.trust,
        )
        return app, events, proxy

    def _launch(self, client: TestClient, agent_id: str):
        return client.post(
            "/runs",
            json={"kind": "lane_b", "params": {"agent_id": agent_id, "stub_script": _STUB_SCRIPT}},
        )

    def _place(self, agent_id: str, fixture: Path) -> None:
        shutil.copyfile(fixture, self.passport_dir / f"{agent_id}.json")

    def _admissions(self, events: InMemoryEventStore) -> list:
        return events.read_from(kind=EventKind.AGENT_ADMISSION.value)

    def _denied_reasons(self, events: InMemoryEventStore) -> list[str]:
        out: list[str] = []
        for ev in events.read_from(kind=EventKind.ACTION_DENIED):
            reason = ev.payload.get("extra", {}).get("deny_reason")
            if reason is not None:
                out.append(str(reason))
        return out

    def _action(self, agent_id: str, timestamp: str) -> ActionRequest:
        return ActionRequest(
            agent_id=agent_id,
            action_type="read_repo",
            target_system="gitlab",
            resource="gitlab/acme/repo",
            payload={},
            timestamp=timestamp,
        )

    # --- Row 2: observe + expired fixture -> 201, audited untrusted, admitted ---

    def test_observe_expired_fixture_launch_admits_and_audits(self) -> None:
        agent_id = "observe-expired"
        self._place(agent_id, _EXPIRED_FIXTURE)
        app, events, _ = self._app(enforce=False, agent_id=agent_id)
        resp = self._launch(TestClient(app), agent_id)
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()["admission"]
        self.assertEqual(body["status"], "untrusted")
        self.assertTrue(body["admitted"])  # observe admits despite untrusted
        self.assertEqual(body["mode"], "observe")
        admissions = self._admissions(events)
        self.assertEqual(len(admissions), 1)
        payload = admissions[0].payload
        self.assertEqual(payload["status"], "untrusted")
        self.assertTrue(payload["admitted"])
        self.assertIn({"kind": "expired"}, payload["reasons"])

    # --- Row 4: enforce + expired fixture -> 403, audited (admitted False) first ---

    def test_enforce_expired_fixture_launch_denies_403_audited(self) -> None:
        agent_id = "enforce-expired"
        self._place(agent_id, _EXPIRED_FIXTURE)
        app, events, _ = self._app(enforce=True, agent_id=agent_id)
        resp = self._launch(TestClient(app), agent_id)
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertIn("admission denied", resp.json()["detail"])
        # The denial is on the append-only log BEFORE the 403 raise (I1).
        admissions = self._admissions(events)
        self.assertEqual(len(admissions), 1)
        payload = admissions[0].payload
        self.assertEqual(payload["status"], "untrusted")
        self.assertFalse(payload["admitted"])
        self.assertEqual(payload["mode"], "enforce")
        self.assertIn({"kind": "expired"}, payload["reasons"])

    # --- Rows 5 + 6: enforce + trusted fixture -> 201 launch, action passes then
    #     mid-run expiry denies (the key end-to-end proof) --------------------

    def test_enforce_trusted_fixture_admits_then_mid_run_expiry_denies(self) -> None:
        agent_id = "trusted-agent"  # matches the fixture id; passport at <dir>/<id>.json
        self._place(agent_id, _TRUSTED_FIXTURE)
        app, events, proxy = self._app(enforce=True, agent_id=agent_id)
        client = TestClient(app)

        # Row 5 launch: trusted at wall-clock launch (2026 < exp 2035) -> 201.
        resp = self._launch(client, agent_id)
        self.assertEqual(resp.status_code, 201, resp.text)
        launch = resp.json()["admission"]
        self.assertEqual(launch["status"], "trusted")
        self.assertTrue(launch["admitted"])
        self.assertEqual(launch["mode"], "enforce")

        # Row 5 action: still valid mid-run (ts < exp) -> the passport gate does
        # NOT veto. "Passes the passport middleware" = no untrusted_passport veto;
        # the downstream policy verdict is out of scope for the admission recette.
        valid = app.state.gateway.submit(self._action(agent_id, _BEFORE_EXP))
        self.assertNotIn("untrusted_passport", valid.error or "")
        self.assertTrue(all("untrusted_passport" not in r for r in self._denied_reasons(events)))

        # Row 6 action: lapsed mid-run (ts > exp) on the SAME cached passport ->
        # the middleware re-attests it as expired and vetoes BEFORE policy/proxy.
        expired = app.state.gateway.submit(self._action(agent_id, _AFTER_EXP))
        self.assertEqual(expired.verdict, PolicyVerdict.DENY)
        self.assertIn("untrusted_passport", expired.error or "")
        self.assertIn("expired", expired.error or "")
        self.assertEqual(proxy.calls, [])  # the lapsed action never executed (fail-safe)
        mid_run = [r for r in self._denied_reasons(events) if "untrusted_passport" in r]
        self.assertEqual(len(mid_run), 1)
        self.assertIn("expired", mid_run[0])

    # --- Replay determinism (I4): primitive + byte-identical payload ---------

    def test_replay_primitive_and_payload_byte_identical(self) -> None:
        agent_id = "trusted-agent"
        passport = json.loads(_TRUSTED_FIXTURE.read_text(encoding="utf-8"))
        declared = list(passport["scope"])
        # Injected clock (I4): NOT the wall clock. Same inputs replayed twice.
        first = admit_agent(passport, declared, self.trust, _BEFORE_EXP, enforce=True)
        second = admit_agent(passport, declared, self.trust, _BEFORE_EXP, enforce=True)
        self.assertEqual(first, second)
        self.assertIsInstance(first, AdmissionVerdict)
        self.assertEqual(first.status, "trusted")
        # The AGENT_ADMISSION payload is byte-stable across the replay.
        p1 = json.dumps(_admission_payload(agent_id, first), sort_keys=True)
        p2 = json.dumps(_admission_payload(agent_id, second), sort_keys=True)
        self.assertEqual(p1, p2)

    def test_replay_two_unsigned_launches_identical_admission_payload(self) -> None:
        # Two identical observe launches of an UNSIGNED agent (no passport file).
        # `unsigned` does not depend on `now`, so the admission payload is invariant
        # to the boundary wall clock -- a legitimate endpoint-level replay that
        # asserts no wall-clock value (I4 boundary documented in the module docstring).
        agent_id = "unsigned-agent"
        app, events, _ = self._app(enforce=False, agent_id=agent_id)
        client = TestClient(app)
        first = self._launch(client, agent_id)
        second = self._launch(client, agent_id)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["admission"], second.json()["admission"])
        self.assertEqual(first.json()["admission"]["status"], "unsigned")
        admissions = self._admissions(events)
        self.assertEqual(len(admissions), 2)
        p0 = json.dumps(admissions[0].payload, sort_keys=True)
        p1 = json.dumps(admissions[1].payload, sort_keys=True)
        self.assertEqual(p0, p1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
