"""CLI parser tests: argument surface for `python -m recette agent run`.

Parse-level only -- no network, no API keys. These assert the argparse contract:
the 8 LLM providers are accepted, unknown ones rejected, and --base-url parses.
The live build_llm wiring (provider -> backend, base_url threading) is covered by
test_llm.py; here we only guard the CLI argument surface and openai_compat validation.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from recette.__main__ import build_parser, main

# Derive from the factory's source of truth so a new vendor is exercised here
# automatically (the CLI --provider choices come from the same tuple).
from recette.llm import _PROVIDERS


class TestAgentRunParser(unittest.TestCase):
    def test_all_providers_accepted(self) -> None:
        parser = build_parser()
        for provider in _PROVIDERS:
            with self.subTest(provider=provider):
                args = parser.parse_args(
                    ["agent", "run", "m.json", "--provider", provider, "--model", "x"]
                )
                self.assertEqual(args.provider, provider)

    def test_unknown_provider_rejected(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                parser.parse_args(["agent", "run", "m.json", "--provider", "bogus", "--model", "x"])

    def test_base_url_parses_and_defaults_none(self) -> None:
        parser = build_parser()
        default = parser.parse_args(
            ["agent", "run", "m.json", "--provider", "openai", "--model", "x"]
        )
        self.assertIsNone(default.base_url)
        with_url = parser.parse_args(
            [
                "agent",
                "run",
                "m.json",
                "--provider",
                "openai_compat",
                "--model",
                "x",
                "--base-url",
                "http://localhost:11434/v1",
            ]
        )
        self.assertEqual(with_url.base_url, "http://localhost:11434/v1")


class TestAgentRunOpenaiCompatValidation(unittest.TestCase):
    def test_openai_compat_without_base_url_errors_nonzero(self) -> None:
        # No --base-url for openai_compat must fail cleanly with a non-zero exit,
        # without reaching the network. main() returns the process exit code.
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = main(["agent", "run", "m.json", "--provider", "openai_compat", "--model", "x"])
        self.assertNotEqual(code, 0)
        self.assertIn("base_url", stderr.getvalue() + "")


if __name__ == "__main__":
    unittest.main()
