"""CLI: python -m recette receipts-verify <export.json>.

The terminal twin of POST /proxy/receipts/verify-import -- an auditor verifies a
signed receipt export OFF-platform with only the file (+ optional public key).
Exit 0 iff the Ed25519 signature is valid AND the hash chain is intact. Pure
given the file (I4): no network, no console, no recorder.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from recette.__main__ import main
from recette.context_receipt import chain_receipts
from recette.receipt_export import SIGNING_KEY_ENV, export_receipts

try:
    import cryptography.hazmat.primitives.asymmetric.ed25519  # noqa: F401

    _HAVE_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAVE_CRYPTO = False

_TRACE = {
    "seq": 1,
    "event_id": "evt-0001",
    "timestamp": "2026-01-01T00:00:00Z",
    "agent_id": "gh-pr-bot",
    "target_system": "github",
    "target": "api.github.com",
    "action_type": "open_pr",
    "resource": "acme/x",
    "request_payload": {"a": 1},
    "ok": True,
    "status_code": 201,
    "side_effect_hash": "h",
    "run_id": "run-1",
    "response": {"n": 42},
}
_SEED = "a12a12dbf6c6a9b89c9e3ef84707a4c2fc0d04a5fa0a78536df8930b4bf16a65"


def _write(envelope: dict) -> str:
    tmp = TemporaryDirectory()
    _write.cleanups.append(tmp)  # type: ignore[attr-defined]
    path = Path(tmp.name) / "export.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return str(path)


_write.cleanups = []  # type: ignore[attr-defined]


class TestReceiptsVerifyUnsigned(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(SIGNING_KEY_ENV, None)

    def tearDown(self) -> None:
        if self._saved is not None:
            os.environ[SIGNING_KEY_ENV] = self._saved
        for tmp in _write.cleanups:  # type: ignore[attr-defined]
            tmp.cleanup()
        _write.cleanups.clear()  # type: ignore[attr-defined]

    def test_unsigned_export_is_invalid_exit_1(self) -> None:
        path = _write(export_receipts(chain_receipts([_TRACE])))
        self.assertEqual(main(["receipts-verify", path]), 1)

    def test_non_object_envelope_is_invalid(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "bad.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(main(["receipts-verify", str(path)]), 1)


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography ([bundle] extra) not installed")
class TestReceiptsVerifySigned(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get(SIGNING_KEY_ENV)
        os.environ[SIGNING_KEY_ENV] = _SEED

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(SIGNING_KEY_ENV, None)
        else:
            os.environ[SIGNING_KEY_ENV] = self._saved
        for tmp in _write.cleanups:  # type: ignore[attr-defined]
            tmp.cleanup()
        _write.cleanups.clear()  # type: ignore[attr-defined]

    def test_signed_export_verifies_exit_0(self) -> None:
        path = _write(export_receipts(chain_receipts([_TRACE])))
        self.assertEqual(main(["receipts-verify", path]), 0)

    def test_key_pinning_wrong_key_exit_1(self) -> None:
        path = _write(export_receipts(chain_receipts([_TRACE])))
        self.assertEqual(main(["receipts-verify", path, "--pubkey", "deadbeef"]), 1)

    def test_tampered_export_exit_1(self) -> None:
        env = export_receipts(chain_receipts([_TRACE]))
        env["receipts"][0]["action_type"] = "TAMPERED"
        path = _write(env)
        self.assertEqual(main(["receipts-verify", path]), 1)

    def test_json_flag_emits_verdict(self) -> None:
        path = _write(export_receipts(chain_receipts([_TRACE])))
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["receipts-verify", path, "--json"])
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertTrue(out["signature"]["valid"])
        self.assertTrue(out["chain"]["ok"])


if __name__ == "__main__":
    unittest.main()
