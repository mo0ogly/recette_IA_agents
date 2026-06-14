"""Lab domain hot-reload (dev convenience, gated by INSPECT_IA_AGENTS_LAB_RELOAD).

The mock_local servers are long-lived: they import each domain once. With the
flag ON, `_maybe_reload` reloads a domain module whose source mtime changed so an
edited handler is served without a server restart. With the flag OFF (the
default, used by tests and replay) it is a strict no-op -- the lab stays static
and deterministic (I4). These tests assert the gate and the change-trigger
without touching real files (mtime/reload are patched).
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from recette.lab import mock_server


class LabHotReloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.pop("INSPECT_IA_AGENTS_LAB_RELOAD", None)
        self._mtimes = dict(mock_server._MTIMES)
        self._handlers = dict(mock_server._HANDLERS)

    def tearDown(self) -> None:
        if self._env is None:
            os.environ.pop("INSPECT_IA_AGENTS_LAB_RELOAD", None)
        else:
            os.environ["INSPECT_IA_AGENTS_LAB_RELOAD"] = self._env
        mock_server._MTIMES.clear()
        mock_server._MTIMES.update(self._mtimes)
        mock_server._HANDLERS.clear()
        mock_server._HANDLERS.update(self._handlers)

    def test_no_reload_when_flag_disabled(self) -> None:
        os.environ.pop("INSPECT_IA_AGENTS_LAB_RELOAD", None)
        with mock.patch.object(mock_server.importlib, "reload") as reload_mock:
            mock_server._maybe_reload()
        reload_mock.assert_not_called()

    def test_no_reload_when_mtime_unchanged(self) -> None:
        os.environ["INSPECT_IA_AGENTS_LAB_RELOAD"] = "on"
        # getmtime returns exactly what was seeded -> nothing changed.
        with (
            mock.patch.object(
                mock_server.os.path, "getmtime", side_effect=lambda p: self._mtimes.get(p, 0.0)
            ),
            mock.patch.object(mock_server.importlib, "reload") as reload_mock,
        ):
            mock_server._maybe_reload()
        reload_mock.assert_not_called()

    def test_reloads_changed_module_when_enabled(self) -> None:
        os.environ["INSPECT_IA_AGENTS_LAB_RELOAD"] = "on"
        # Every tracked module looks changed -> each is reloaded exactly once.
        with (
            mock.patch.object(mock_server.os.path, "getmtime", return_value=9.0e9),
            mock.patch.object(
                mock_server.importlib, "reload", side_effect=lambda m: m
            ) as reload_mock,
        ):
            mock_server._maybe_reload()
        self.assertEqual(reload_mock.call_count, len(self._handlers))
        # The new mtime is recorded, so a second pass is a no-op (no re-reload).
        with (
            mock.patch.object(mock_server.os.path, "getmtime", return_value=9.0e9),
            mock.patch.object(
                mock_server.importlib, "reload", side_effect=lambda m: m
            ) as reload_again,
        ):
            mock_server._maybe_reload()
        reload_again.assert_not_called()


if __name__ == "__main__":
    unittest.main()
