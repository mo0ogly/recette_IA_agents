import os
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
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

    def test_windows_launches_the_script_through_bash(self) -> None:
        # recette.sh is a POSIX script: spawning it directly on Windows fails
        # with WinError 193, so the router must route it through bash.
        with (
            mock.patch.dict(os.environ, {"INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL": "1"}),
            mock.patch("recette.api.routers.proxy.os.name", "nt"),
            mock.patch(
                "recette.api.routers.proxy.shutil.which",
                return_value="C:\\Git\\bin\\bash.exe",
            ),
            mock.patch("recette.api.routers.proxy.subprocess.run") as run,
        ):
            run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
            r = self.client.post("/proxy/wire/overlay", json={"action": "up"})
        self.assertEqual(r.status_code, 200)
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], "C:\\Git\\bin\\bash.exe")
        self.assertEqual(argv[1:], ["./recette.sh", "wire", "up"])

    def test_windows_without_bash_is_an_explicit_502(self) -> None:
        # Fail-safe: no bash on PATH -> actionable 502, never a WinError leak
        # or a silent fallback launcher.
        with (
            mock.patch.dict(os.environ, {"INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL": "1"}),
            mock.patch("recette.api.routers.proxy.os.name", "nt"),
            mock.patch("recette.api.routers.proxy.shutil.which", return_value=None),
            mock.patch("recette.api.routers.proxy.subprocess.run") as run,
        ):
            r = self.client.post("/proxy/wire/overlay", json={"action": "up"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("bash", r.json()["detail"])
        self.assertFalse(run.called)


if __name__ == "__main__":
    unittest.main()
