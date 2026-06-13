"""G1 -- identity binding (I3): the JWT verifier and the API auth middleware.

Two layers:
  - the pure verifier (recette/api/auth.py): roundtrip, and every forgery path
    (alg-confusion, alg:none, tampered signature, expired, no subject) is refused;
  - the middleware: deny-by-default (401) once a signing key is configured, the
    allowlist stays open, an authenticated agent may only act as itself (403 on a
    mismatched agent_id), and with no key the API stays open (dev/test).
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from recette.api.auth import (
    AuthError,
    Principal,
    decode_token,
    issue_token,
    principal_from_claims,
)

KEY = "unit-test-signing-key-0123456789"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class TestJwtVerifier(unittest.TestCase):
    def test_roundtrip(self) -> None:
        token = issue_token({"sub": "op1", "kind": "operator"}, KEY)
        claims = decode_token(token, KEY)
        self.assertEqual(claims["sub"], "op1")
        self.assertEqual(claims["kind"], "operator")

    def test_wrong_key_rejected(self) -> None:
        token = issue_token({"sub": "op1"}, KEY)
        with self.assertRaises(AuthError):
            decode_token(token, "another-key-0123456789aaaa")

    def test_tampered_payload_rejected(self) -> None:
        header, payload, sig = issue_token({"sub": "op1", "kind": "operator"}, KEY).split(".")
        forged_payload = _b64(json.dumps({"sub": "admin", "kind": "operator"}).encode())
        with self.assertRaises(AuthError):
            decode_token(f"{header}.{forged_payload}.{sig}", KEY)

    def test_alg_none_rejected(self) -> None:
        # The classic alg:none forgery: empty signature, header claims no alg.
        header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        payload = _b64(json.dumps({"sub": "admin"}).encode())
        with self.assertRaises(AuthError):
            decode_token(f"{header}.{payload}.", KEY)

    def test_alg_confusion_rejected(self) -> None:
        # A token that claims RS256 must never be accepted by an HS256 verifier.
        header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        payload = _b64(json.dumps({"sub": "admin"}).encode())
        with self.assertRaises(AuthError):
            decode_token(f"{header}.{payload}.whatever", KEY)

    def test_expired_rejected(self) -> None:
        token = issue_token({"sub": "op1"}, KEY, ttl_seconds=10, now=1000)
        with self.assertRaises(AuthError):
            decode_token(token, KEY, now=2000)

    def test_not_yet_valid_rejected(self) -> None:
        # nbf in the future relative to the verification clock -> not yet valid.
        token = issue_token({"sub": "op1", "nbf": 5000}, KEY, now=0)
        with self.assertRaises(AuthError):
            decode_token(token, KEY, now=1000)

    def test_missing_subject_rejected(self) -> None:
        token = issue_token({"kind": "operator"}, KEY)
        with self.assertRaises(AuthError):
            decode_token(token, KEY)

    def test_short_key_rejected(self) -> None:
        with self.assertRaises(AuthError):
            issue_token({"sub": "x"}, "short")

    def test_principal_agent_binds_agent_id(self) -> None:
        p = principal_from_claims({"sub": "agentA", "kind": "agent"})
        self.assertEqual(p, Principal(sub="agentA", kind="agent", agent_id="agentA"))
        p2 = principal_from_claims({"sub": "svc", "kind": "agent", "agent_id": "bot-7"})
        self.assertEqual(p2.agent_id, "bot-7")

    def test_principal_unknown_kind_rejected(self) -> None:
        with self.assertRaises(AuthError):
            principal_from_claims({"sub": "x", "kind": "root"})


try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestAuthMiddleware(unittest.TestCase):
    def setUp(self) -> None:
        self._prev = os.environ.get("AGENTRAIL_JWT_SIGNING_KEY")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("AGENTRAIL_JWT_SIGNING_KEY", None)
        else:
            os.environ["AGENTRAIL_JWT_SIGNING_KEY"] = self._prev

    def _client(self, *, key: str | None) -> TestClient:
        if key is None:
            os.environ.pop("AGENTRAIL_JWT_SIGNING_KEY", None)
        else:
            os.environ["AGENTRAIL_JWT_SIGNING_KEY"] = key
        from recette.api.config_store import ConfigStore

        app = create_app(
            config_store=ConfigStore(Path(self._tmp.name) / "config.json"),
            event_store=InMemoryEventStore(),
        )
        return TestClient(app)

    def test_open_mode_no_key_allows_unauthenticated(self) -> None:
        client = self._client(key=None)
        self.assertLess(client.get("/policies").status_code, 400)

    def test_health_open_even_with_key(self) -> None:
        client = self._client(key=KEY)
        self.assertEqual(client.get("/health").status_code, 200)

    def test_protected_route_without_token_is_401(self) -> None:
        client = self._client(key=KEY)
        self.assertEqual(client.get("/policies").status_code, 401)

    def test_protected_route_with_operator_token_passes_auth(self) -> None:
        client = self._client(key=KEY)
        token = issue_token({"sub": "op1", "kind": "operator"}, KEY)
        resp = client.get("/policies", headers={"Authorization": f"Bearer {token}"})
        self.assertLess(resp.status_code, 400)

    def test_bad_token_is_401(self) -> None:
        client = self._client(key=KEY)
        resp = client.get("/policies", headers={"Authorization": "Bearer not.a.jwt"})
        self.assertEqual(resp.status_code, 401)

    def test_agent_can_only_act_as_itself(self) -> None:
        client = self._client(key=KEY)
        token = issue_token({"sub": "agentA", "kind": "agent", "agent_id": "agentA"}, KEY)
        headers = {"Authorization": f"Bearer {token}"}
        body = {
            "agent_id": "agentB",  # impersonation attempt
            "action_type": "read_repo",
            "target_system": "github",
            "resource": "x",
        }
        mismatch = client.post("/actions/execute", json=body, headers=headers)
        self.assertEqual(mismatch.status_code, 403)
        body["agent_id"] = "agentA"  # acting as itself: identity binding passes
        ok = client.post("/actions/execute", json=body, headers=headers)
        self.assertNotIn(ok.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
