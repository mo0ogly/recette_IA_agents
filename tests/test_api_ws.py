"""U1: WebSocket streams a run's event frames to completion."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRunWebSocket(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_ws_streams_until_end(self) -> None:
        run_id = self.client.post("/runs", json={"kind": "identification", "params": {}}).json()[
            "run_id"
        ]
        frames = []
        with self.client.websocket_connect(f"/runs/{run_id}/ws") as ws:
            while True:
                frame = ws.receive_json()
                frames.append(frame)
                if frame["type"] == "end":
                    break
        types = [f["type"] for f in frames]
        self.assertEqual(types[0], "start")
        self.assertIn("scorecard", types)
        self.assertEqual(types[-1], "end")
        self.assertEqual(frames[-1]["data"]["status"], "completed")
