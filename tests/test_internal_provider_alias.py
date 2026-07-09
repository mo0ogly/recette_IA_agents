# tests/test_internal_provider_alias.py
"""'internal' is a zero-breakage alias of the 'skynet' provider.

A neutral display name that resolves identically (same SkynetLlm class, same
per-model endpoints, same SKYNET_API_KEY env). Existing 'skynet' backends are
untouched; 'internal' appears in the console provider catalog and builds through
the same path."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.llm import _PROVIDER_CLASSES, _PROVIDERS, build_llm, provider_models
from recette.llm._registry import _BASE_URL_DRIVEN_PROVIDERS

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False

_SKYNET_URL = "https://api.skynet.cossi.internet/gpt-oss-120b/v1"


class TestInternalAliasRegistry(unittest.TestCase):
    def test_internal_is_a_first_class_provider_mapped_to_skynet(self) -> None:
        self.assertIn("internal", _PROVIDERS)
        self.assertIn("skynet", _PROVIDERS)  # kept, not replaced (zero breakage)
        # Drift guard invariant: classes cover exactly the providers.
        self.assertEqual(set(_PROVIDER_CLASSES), set(_PROVIDERS))
        self.assertIs(_PROVIDER_CLASSES["internal"], _PROVIDER_CLASSES["skynet"])
        self.assertIn("internal", _BASE_URL_DRIVEN_PROVIDERS)

    def test_internal_shares_skynet_models(self) -> None:
        self.assertEqual(provider_models("internal"), provider_models("skynet"))
        self.assertTrue(provider_models("internal"))  # non-empty

    def test_build_llm_internal_resolves_like_skynet(self) -> None:
        internal = build_llm("internal", "openai/gpt-oss-120b", base_url=_SKYNET_URL)
        skynet = build_llm("skynet", "openai/gpt-oss-120b", base_url=_SKYNET_URL)
        self.assertIs(type(internal), type(skynet))

    def test_build_llm_internal_requires_base_url_like_skynet(self) -> None:
        with self.assertRaises(ValueError):
            build_llm("internal", "openai/gpt-oss-120b")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestInternalAliasCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_catalog_exposes_internal_like_skynet(self) -> None:
        catalog = self.client.get("/config/ai-providers").json()
        by_id = {p["id"]: p for p in catalog}
        self.assertIn("internal", by_id)
        self.assertIn("skynet", by_id)
        internal, skynet = by_id["internal"], by_id["skynet"]
        # Same env var (key resolves the same), same models, same per-model routes.
        self.assertEqual(internal["env_key"], "SKYNET_API_KEY")
        self.assertEqual(internal["models"], skynet["models"])
        self.assertEqual(internal["model_endpoints"], skynet["model_endpoints"])
