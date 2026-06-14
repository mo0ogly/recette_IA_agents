"""Unit tests for the runtime proxy-route registry (recette/platform/proxy/route.py)."""

from __future__ import annotations

import os
import unittest

from recette.platform.proxy.route import (
    DEFAULT_WIRE_URL,
    DIRECT_ID,
    WIRE_ID,
    ProxyRouteRegistry,
    registry_from_env,
)


class ProxyRouteRegistryTests(unittest.TestCase):
    def test_default_is_direct_when_env_absent(self) -> None:
        reg = ProxyRouteRegistry()
        self.assertEqual(reg.active(), DIRECT_ID)
        self.assertIsNone(reg.active_proxy_url())

    def test_starts_on_wire_when_opted_in(self) -> None:
        reg = ProxyRouteRegistry(wire_url="http://127.0.0.1:9999", active_from_env=True)
        self.assertEqual(reg.active(), WIRE_ID)
        self.assertEqual(reg.active_proxy_url(), "http://127.0.0.1:9999")

    def test_wire_target_falls_back_to_canonical_url(self) -> None:
        reg = ProxyRouteRegistry()
        wire = next(t for t in reg.targets() if t.id == WIRE_ID)
        self.assertEqual(wire.proxy_url, DEFAULT_WIRE_URL)

    def test_always_offers_direct_and_wire(self) -> None:
        ids = {t.id for t in ProxyRouteRegistry().targets()}
        self.assertEqual(ids, {DIRECT_ID, WIRE_ID})

    def test_set_active_switches_route(self) -> None:
        reg = ProxyRouteRegistry()
        reg.set_active(WIRE_ID)
        self.assertEqual(reg.active(), WIRE_ID)
        self.assertEqual(reg.active_proxy_url(), DEFAULT_WIRE_URL)
        reg.set_active(DIRECT_ID)
        self.assertIsNone(reg.active_proxy_url())

    def test_unknown_target_raises(self) -> None:
        with self.assertRaises(ValueError):
            ProxyRouteRegistry().set_active("nope")

    def test_targets_to_dict_shape(self) -> None:
        d = ProxyRouteRegistry().targets()[0].to_dict()
        self.assertEqual(set(d), {"id", "label", "proxy_url"})

    def test_registry_from_env_direct_without_wire_env(self) -> None:
        saved = os.environ.pop("INSPECT_IA_AGENTS_WIRE_PROXY", None)
        try:
            reg = registry_from_env()
            self.assertEqual(reg.active(), DIRECT_ID)
        finally:
            if saved is not None:
                os.environ["INSPECT_IA_AGENTS_WIRE_PROXY"] = saved

    def test_registry_from_env_wire_when_env_set(self) -> None:
        saved = os.environ.get("INSPECT_IA_AGENTS_WIRE_PROXY")
        os.environ["INSPECT_IA_AGENTS_WIRE_PROXY"] = "http://127.0.0.1:8083"
        try:
            reg = registry_from_env()
            self.assertEqual(reg.active(), WIRE_ID)
            self.assertEqual(reg.active_proxy_url(), "http://127.0.0.1:8083")
        finally:
            if saved is None:
                os.environ.pop("INSPECT_IA_AGENTS_WIRE_PROXY", None)
            else:
                os.environ["INSPECT_IA_AGENTS_WIRE_PROXY"] = saved


if __name__ == "__main__":
    unittest.main()
