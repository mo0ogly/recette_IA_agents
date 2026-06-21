"""Tests for the mitmproxy wire addon (scripts/mitm_wire_addon.py).

No mitmproxy runtime: build_ingest_payload is pure, and the WireCapture hook is
driven with a duck-typed fake flow while the network POST is stubbed. Verifies
the normalized shape, run-id header extraction, body clipping, and the fail-safe
guards (missing response, undecodable body) never crash the hook.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "mitm_wire_addon",
    Path(__file__).resolve().parent.parent / "scripts" / "mitm_wire_addon.py",
)
assert _SPEC is not None and _SPEC.loader is not None
addon = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(addon)


class _FakeHeaders:
    def __init__(self, data: dict[str, str]) -> None:
        self._data = {k.lower(): v for k, v in data.items()}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._data.get(key.lower(), default)


class _FakeMessage:
    def __init__(self, text: str, headers: dict[str, str] | None = None, **attrs: object) -> None:
        self._text = text
        self.headers = _FakeHeaders(headers or {})
        for k, v in attrs.items():
            setattr(self, k, v)

    def get_text(self, strict: bool = True) -> str:
        return self._text


class _FakeFlow:
    def __init__(self, request: object, response: object | None) -> None:
        self.request = request
        self.response = response


class BuildIngestPayloadTests(unittest.TestCase):
    def test_shape(self) -> None:
        payload = addon.build_ingest_payload(
            method="POST",
            scheme="http",
            host="localhost",
            port=8082,
            path="/github/execute",
            status_code=200,
            content_type="application/json",
            request_body="req",
            response_body="resp",
            run_id="run-1",
        )
        self.assertEqual(payload["method"], "POST")
        self.assertEqual(payload["status_code"], 200)
        self.assertEqual(payload["run_id"], "run-1")

    def test_duration_ms_included_when_given(self) -> None:
        payload = addon.build_ingest_payload(
            method="POST",
            scheme="http",
            host="localhost",
            port=8082,
            path="/github/execute",
            status_code=200,
            content_type="application/json",
            request_body="req",
            response_body="resp",
            run_id="run-1",
            duration_ms=12.5,
        )
        self.assertEqual(payload["duration_ms"], 12.5)

    def test_duration_ms_present_as_none_when_omitted(self) -> None:
        # Key is always present (shape stability), defaulting to None.
        payload = addon.build_ingest_payload(
            method="GET",
            scheme="http",
            host="h",
            port=80,
            path="/",
            status_code=200,
            content_type="",
            request_body="",
            response_body="",
            run_id=None,
        )
        self.assertIn("duration_ms", payload)
        self.assertIsNone(payload["duration_ms"])

    def test_body_is_clipped(self) -> None:
        big = "y" * (addon.MAX_BODY_CHARS + 50)
        payload = addon.build_ingest_payload(
            method="GET",
            scheme="http",
            host="h",
            port=80,
            path="/",
            status_code=200,
            content_type="",
            request_body=big,
            response_body=big,
            run_id=None,
        )
        self.assertEqual(len(payload["request_body"]), addon.MAX_BODY_CHARS)
        self.assertEqual(len(payload["response_body"]), addon.MAX_BODY_CHARS)


class WireCaptureHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.posted: list[dict] = []
        self._orig_post = addon._post
        addon._post = self.posted.append  # type: ignore[assignment,attr-defined]

    def tearDown(self) -> None:
        addon._post = self._orig_post  # type: ignore[assignment,attr-defined]

    def test_full_flow_is_posted(self) -> None:
        req = _FakeMessage(
            "request-body",
            headers={"x-inspect-run-id": "run-9"},
            method="POST",
            scheme="http",
            host="localhost",
            port=8082,
            path="/github/execute",
        )
        resp = _FakeMessage(
            '{"success":true}',
            headers={"content-type": "application/json"},
            status_code=201,
        )
        addon.WireCapture().response(_FakeFlow(req, resp))
        self.assertEqual(len(self.posted), 1)
        sent = self.posted[0]
        self.assertEqual(sent["host"], "localhost")
        self.assertEqual(sent["status_code"], 201)
        self.assertEqual(sent["run_id"], "run-9")
        self.assertEqual(sent["response_body"], '{"success":true}')

    def test_duration_ms_computed_from_flow_timestamps(self) -> None:
        # The hook computes round-trip latency from request start / response end
        # timestamps (wall-clock OPS metadata on the view only, never a judge
        # input, I4).
        req = _FakeMessage(
            "x",
            method="GET",
            scheme="http",
            host="h",
            port=80,
            path="/",
            timestamp_start=100.0,
        )
        resp = _FakeMessage("ok", status_code=200, timestamp_end=100.0125)
        addon.WireCapture().response(_FakeFlow(req, resp))
        self.assertEqual(self.posted[0]["duration_ms"], 12.5)

    def test_duration_ms_none_when_timestamps_absent(self) -> None:
        req = _FakeMessage("x", method="GET", scheme="http", host="h", port=80, path="/")
        resp = _FakeMessage("ok", status_code=200)
        addon.WireCapture().response(_FakeFlow(req, resp))
        self.assertIsNone(self.posted[0]["duration_ms"])

    def test_missing_response_is_skipped(self) -> None:
        req = _FakeMessage("x", method="GET", host="h", port=80, path="/", scheme="http")
        addon.WireCapture().response(_FakeFlow(req, None))
        self.assertEqual(self.posted, [])

    def test_no_run_header_yields_none(self) -> None:
        req = _FakeMessage("x", method="GET", scheme="http", host="h", port=80, path="/")
        resp = _FakeMessage("ok", status_code=200)
        addon.WireCapture().response(_FakeFlow(req, resp))
        self.assertIsNone(self.posted[0]["run_id"])

    def test_undecodable_body_does_not_crash(self) -> None:
        class _Boom:
            headers = _FakeHeaders({})
            status_code = 200

            def get_text(self, strict: bool = True) -> str:
                raise ValueError("binary")

        req = _Boom()
        req.method, req.scheme, req.host, req.port, req.path = "GET", "http", "h", 80, "/"  # type: ignore[attr-defined]
        addon.WireCapture().response(_FakeFlow(req, _Boom()))
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(self.posted[0]["response_body"], "")


if __name__ == "__main__":
    unittest.main()
