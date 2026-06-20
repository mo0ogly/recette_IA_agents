"""POST /probe/process-capture-campaign: spawn every campaign step as a process
and capture them by PID in one eBPF window.

Two layers, both privilege-free:
- the pure step resolver ``_capturable_step_cfg`` (deterministic decision: which
  steps can run mock, which are skipped -- never faked), tested directly;
- the endpoint contract (503 without a broker, 400 on an unknown campaign),
  tested via TestClient with a fake socket so no real broker is needed.

A live capture itself is non-deterministic (kernel measurement) and is proven in
the smoke / runbook, not here (R20: the pure decision is what we unit-test).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from recette.api.runners import _capturable_step_cfg

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False

_SOCKET_ENV = "INSPECT_IA_AGENTS_PROBE_SOCKET"


class CapturableStepCfgTest(unittest.TestCase):
    """The pure resolver: mock-capable -> cfg; real/no-scenario -> None."""

    def test_stub_script_forces_mock_and_overrides_scenario(self) -> None:
        cfg = _capturable_step_cfg(
            {"id": "a", "ai_mode": "real", "scenario": [{"kind": "final"}]},
            [{"kind": "tool_call", "tool_name": "read_repo"}],
        )
        assert cfg is not None
        self.assertEqual(cfg["ai_mode"], "mock")
        self.assertEqual(cfg["scenario"], [{"kind": "tool_call", "tool_name": "read_repo"}])

    def test_mock_with_scenario_is_capturable(self) -> None:
        cfg = _capturable_step_cfg(
            {"id": "a", "ai_mode": "mock", "scenario": [{"kind": "final"}]}, None
        )
        self.assertIsNotNone(cfg)

    def test_real_without_stub_is_skipped(self) -> None:
        self.assertIsNone(
            _capturable_step_cfg({"id": "a", "ai_mode": "real", "scenario": [{"kind": "f"}]}, None)
        )

    def test_mock_without_scenario_is_skipped(self) -> None:
        self.assertIsNone(_capturable_step_cfg({"id": "a", "ai_mode": "mock"}, None))

    def test_resolver_does_not_mutate_input(self) -> None:
        base = {"id": "a", "ai_mode": "real", "scenario": [{"kind": "final"}]}
        _capturable_step_cfg(base, [{"kind": "tool_call"}])
        self.assertEqual(base["ai_mode"], "real")  # original untouched


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra")
class ProcessCaptureCampaignEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self._saved = os.environ.pop(_SOCKET_ENV, None)
        # Neutralize the canonical-socket fallback so "no broker" is deterministic.
        self._canon = mock.patch(
            "recette.api.routers.probe._canonical_socket",
            return_value=Path(tempfile.mkdtemp()) / "absent.sock",
        )
        self._canon.start()
        self.addCleanup(self._canon.stop)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(_SOCKET_ENV, None)
        else:
            os.environ[_SOCKET_ENV] = self._saved

    def test_without_broker_is_503(self) -> None:
        resp = self.client.post("/probe/process-capture-campaign", json={"campaign_id": "whatever"})
        self.assertEqual(resp.status_code, 503)

    def test_unknown_campaign_is_400(self) -> None:
        # A configured socket (campaign is checked before any relay), unknown id.
        os.environ[_SOCKET_ENV] = "/tmp/inspect-ia-agents-absent.sock"  # nosec B108 - never connected
        resp = self.client.post(
            "/probe/process-capture-campaign", json={"campaign_id": "no-such-campaign-xyz"}
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
