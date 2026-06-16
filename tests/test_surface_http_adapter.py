"""HttpSurfaceDiscoveryAdapter: parses a real RailNode detection response and
unwraps the {success, data} envelope. Driven by an injected stub client (no
network), like the recette's other HTTP-adapter tests."""

from __future__ import annotations

import unittest
from typing import Any

from recette.surface.http_adapter import HttpSurfaceDiscoveryAdapter
from recette.surface.surfaces import ObservationSurface, SurfaceObservation


class _StubResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _StubClient:
    """Records the last POST and returns a canned payload."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.last_path: str | None = None
        self.last_body: dict | None = None

    def post(self, path: str, json: dict) -> _StubResponse:
        self.last_path = path
        self.last_body = json
        return _StubResponse(self._payload)


OBS = SurfaceObservation(ObservationSurface.EBPF_WIRE, ("POST shadow-db:5432/w",))


class TestHttpSurfaceAdapter(unittest.TestCase):
    def test_parses_a_detected_response(self) -> None:
        client = _StubClient({"detected": True, "signals": ["POST shadow-db:5432/w"]})
        adapter = HttpSurfaceDiscoveryAdapter(client=client)
        result = adapter.detect_on(OBS)
        self.assertTrue(result.detected)
        self.assertEqual(result.signals, ["POST shadow-db:5432/w"])
        # The observation is sent as {surface, visible} to the detect route.
        self.assertEqual(client.last_path, "/v1/detect")
        self.assertEqual(client.last_body["surface"], "ebpf_wire")
        self.assertEqual(client.last_body["visible"], ["POST shadow-db:5432/w"])

    def test_unwraps_success_data_envelope(self) -> None:
        client = _StubClient({"success": True, "data": {"detected": True, "signals": []}})
        adapter = HttpSurfaceDiscoveryAdapter(client=client)
        self.assertTrue(adapter.detect_on(OBS).detected)

    def test_blind_surface_returns_not_detected(self) -> None:
        client = _StubClient({"detected": False, "signals": []})
        adapter = HttpSurfaceDiscoveryAdapter(client=client)
        result = adapter.detect_on(OBS)
        self.assertFalse(result.detected)
        self.assertEqual(result.signals, [])

    def test_base_url_defaults_and_strips_trailing_slash(self) -> None:
        adapter = HttpSurfaceDiscoveryAdapter(
            base_url="http://railnode.local:8085/", client=object()
        )
        self.assertEqual(adapter.base_url, "http://railnode.local:8085")


if __name__ == "__main__":
    unittest.main()
