"""provider_host derives a backend's host:port from its class BASE_URL (task C).

Used by the reconcile allowlist so a real-mode LLM call is not flagged as an
unmediated path. The drift guard keeps the provider->class map in lockstep with
the provider registry.
"""

from __future__ import annotations

import unittest

from recette.llm import _PROVIDER_CLASSES, _PROVIDERS, provider_host


class ProviderHostTest(unittest.TestCase):
    def test_map_covers_exactly_the_provider_registry(self) -> None:
        # Drift guard: a new provider MUST be added to the host map (else its
        # real-mode traffic would be falsely flagged as unmediated).
        self.assertEqual(set(_PROVIDER_CLASSES), set(_PROVIDERS))

    def test_known_provider_host_has_https_default_port(self) -> None:
        self.assertEqual(provider_host("groq"), "api.groq.com:443")
        self.assertEqual(provider_host("anthropic"), "api.anthropic.com:443")
        self.assertEqual(provider_host("gemini"), "generativelanguage.googleapis.com:443")

    def test_unknown_provider_is_none(self) -> None:
        self.assertIsNone(provider_host("not-a-provider"))

    def test_openai_compat_uses_the_given_base_url(self) -> None:
        # No fixed host: the configured base_url decides.
        self.assertEqual(
            provider_host("openai_compat", "http://127.0.0.1:11434/v1"), "127.0.0.1:11434"
        )
        self.assertIsNone(provider_host("openai_compat"))

    def test_every_mapped_provider_derives_a_host_or_needs_base_url(self) -> None:
        # Every provider with a fixed BASE_URL resolves; only the base_url-driven
        # ones (openai_compat) may be None without an override.
        for provider in _PROVIDERS:
            host = provider_host(provider)
            if provider == "openai_compat":
                self.assertIsNone(host)
            else:
                self.assertIsNotNone(host, f"{provider}: no host derived")
                self.assertIn(":", host or "")


if __name__ == "__main__":
    unittest.main()
