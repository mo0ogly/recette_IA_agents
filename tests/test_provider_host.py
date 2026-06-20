"""provider_host derives a backend's host:port from its class BASE_URL (task C).

Used by the reconcile allowlist so a real-mode LLM call is not flagged as an
unmediated path. The drift guard keeps the provider->class map in lockstep with
the provider registry.
"""

from __future__ import annotations

import unittest

from recette.llm import _PROVIDER_CLASSES, _PROVIDERS, provider_host, provider_models

# Providers that intentionally ship NO curated model list and fall back to a
# free-text model field in the console. Frozen + explicit so it cannot grow
# silently: adding a provider here is a visible decision (the only way to clear
# the no-silent-empty guard without curating model ids). See R13 -- never invent
# model ids; a provider with no authoritative source stays free-text.
_FREE_TEXT_PROVIDERS = frozenset({"openai_compat", "bedrock", "opencode_zen", "qwen", "arcee"})


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


class ProviderModelsTest(unittest.TestCase):
    def test_nous_models_frozen_from_models_dev(self) -> None:
        # Frozen static list (no runtime fetch, I4); the panel gets a dropdown
        # instead of an empty model field. Default = first = the 70B.
        models = provider_models("nous")
        self.assertTrue(models, "nous models must not be empty")
        self.assertEqual(models[0], "Hermes-4-70B")
        # Bare vendor names only -- the provider stays "nous", never "hermes".
        self.assertNotIn("hermes", _PROVIDERS)

    def test_gemini_has_curated_models(self) -> None:
        # Gemini is a major provider: the console must offer a model dropdown,
        # not an empty free-text field. Ids are GA strings verified at the
        # Gemini API models docs (R13), default = first.
        models = provider_models("gemini")
        self.assertTrue(models, "gemini models must not be empty")
        self.assertEqual(models[0], "gemini-2.5-pro")
        self.assertIn("gemini-2.5-flash", models)

    def test_major_providers_carry_curated_models(self) -> None:
        # Frozen from models.dev (R13). Every major provider offers a dropdown.
        for provider in ("xai", "cerebras", "minimax", "together"):
            self.assertTrue(provider_models(provider), f"{provider} must not be empty")
        self.assertEqual(provider_models("xai")[0], "grok-4.3")
        self.assertEqual(provider_models("minimax")[0], "MiniMax-M2")

    def test_free_text_providers_stay_empty_by_design(self) -> None:
        # No canonical curated list: openai_compat (user base_url), bedrock
        # (hundreds of cross-vendor ids), opencode_zen (routes by model), and
        # qwen/arcee (absent from models.dev -- never invent ids, R13). These
        # intentionally fall back to a free-text model field.
        for provider in _FREE_TEXT_PROVIDERS:
            self.assertEqual(provider_models(provider), (), f"{provider} stays free-text")

    def test_no_provider_silently_empty(self) -> None:
        # No-silent-gaps guard (the Gemini failure mode): a major provider shipped
        # with an empty model list -> the console fell back to a free-text field
        # while every peer had a dropdown. Partition every provider into exactly
        # {has curated models} U {explicit free-text allowlist}. A NEW provider
        # added with no models and NOT declared free-text here turns this RED,
        # forcing an explicit choice: curate its ids (R13) or allowlist it.
        curated = {p for p in _PROVIDERS if provider_models(p)}
        classified = curated | _FREE_TEXT_PROVIDERS
        missing = sorted(set(_PROVIDERS) - classified)
        self.assertFalse(
            missing,
            f"providers silently empty -- curate ids or add to _FREE_TEXT_PROVIDERS: {missing}",
        )
        # And the allowlist cannot rot the other way: every declared free-text
        # provider must still exist and still be genuinely empty.
        for provider in _FREE_TEXT_PROVIDERS:
            self.assertIn(provider, set(_PROVIDERS), f"stale free-text allowlist entry: {provider}")
            self.assertEqual(provider_models(provider), (), f"{provider} is no longer free-text")


if __name__ == "__main__":
    unittest.main()
