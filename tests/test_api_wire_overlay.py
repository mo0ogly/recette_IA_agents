import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from recette.api.app import create_app


class WireOverlayControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_denied_by_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL", None)
            r = self.client.post("/proxy/wire/overlay", json={"action": "up"})
        self.assertEqual(r.status_code, 403)

    def test_bad_action_is_422(self) -> None:
        with mock.patch.dict(os.environ, {"INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL": "1"}):
            r = self.client.post("/proxy/wire/overlay", json={"action": "sideways"})
        self.assertEqual(r.status_code, 422)

    def test_bad_action_checked_before_gate(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL", None)
            r = self.client.post("/proxy/wire/overlay", json={"action": "sideways"})
        self.assertEqual(r.status_code, 422)

    def test_up_runs_wire_script_when_allowed(self) -> None:
        with (
            mock.patch.dict(os.environ, {"INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL": "1"}),
            mock.patch("recette.api.routers.proxy.subprocess.run") as run,
        ):
            run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
            r = self.client.post("/proxy/wire/overlay", json={"action": "up"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(run.called)
        # cicd/wire.sh (or ./recette.sh wire) invoked with the action
        self.assertIn("wire", " ".join(str(a) for a in run.call_args[0][0]))


if __name__ == "__main__":
    unittest.main()
