"""Provider-agnostic token usage extraction."""

from __future__ import annotations

import unittest

from recette.capture.usage import extract_usage


class TestExtractUsage(unittest.TestCase):
    def test_openai_style(self) -> None:
        self.assertEqual(
            extract_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 3}}), (10, 3)
        )

    def test_anthropic_style(self) -> None:
        self.assertEqual(extract_usage({"usage": {"input_tokens": 7, "output_tokens": 2}}), (7, 2))

    def test_missing_usage_is_zero(self) -> None:
        self.assertEqual(extract_usage({}), (0, 0))

    def test_malformed_usage_is_zero_not_raise(self) -> None:
        self.assertEqual(extract_usage({"usage": "nope"}), (0, 0))
        self.assertEqual(extract_usage({"usage": {"prompt_tokens": "x"}}), (0, 0))


if __name__ == "__main__":
    unittest.main()
