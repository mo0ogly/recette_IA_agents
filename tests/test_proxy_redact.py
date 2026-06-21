import unittest

from recette.platform.proxy.redact import redact_mapping, redact_text


class RedactTest(unittest.TestCase):
    def test_masks_known_secret_shapes(self) -> None:
        # The AWS shape is built at runtime ("AKIA" + body) so this fixture file
        # does not itself trip a static secret scanner (it is the public AWS docs
        # example value, not a live key).
        aws_example = "AKIA" + "IOSFODNN7EXAMPLE"
        self.assertNotIn("ghp_ABCDEFGHIJKLMNOPQRST", redact_text("token=ghp_ABCDEFGHIJKLMNOPQRST"))
        self.assertNotIn("sk-ABCDEFGHIJKLMNOP", redact_text("key sk-ABCDEFGHIJKLMNOP"))
        self.assertNotIn(aws_example, redact_text(aws_example))
        self.assertNotIn("secrettoken123", redact_text("Authorization: Bearer secrettoken123"))

    def test_masks_unquoted_colon_key_value(self) -> None:
        # YAML/log-line shape: a colon, no quotes. Previously a real leak gap.
        secret = "ghp_" + "ABCDEFGHIJKLMNOPQRST"
        out = redact_text(f"api_key: {secret}")
        self.assertNotIn(secret, out)
        self.assertIn("api_key", out)  # the key label is preserved
        self.assertIn("***REDACTED***", out)

    def test_masks_unquoted_colon_case_insensitive(self) -> None:
        secret = "ghp_" + "ABCDEFGHIJKLMNOPQRST"
        out = redact_text(f"API_KEY: {secret}")
        self.assertNotIn(secret, out)
        self.assertIn("***REDACTED***", out)

    def test_masks_unquoted_equals_password(self) -> None:
        self.assertNotIn("hunter2hunter2", redact_text("password=hunter2hunter2"))

    def test_masks_slack_token(self) -> None:
        token = "xoxb-" + "1234567890-ABCDEFGHIJKLMNOP"
        self.assertNotIn(token, redact_text(token))

    def test_redact_mapping_over_list(self) -> None:
        secret = "sk-" + "ABCDEFGHIJKLMNOP"
        out = redact_mapping([secret, "ok"])
        assert isinstance(out, list)
        self.assertNotIn(secret, str(out[0]))
        self.assertEqual(out[1], "ok")

    def test_redact_mapping_passes_through_non_string_scalars(self) -> None:
        out = redact_mapping({"n": 42, "b": True})
        assert isinstance(out, dict)
        self.assertEqual(out["n"], 42)
        self.assertEqual(out["b"], True)

    def test_redact_text_is_idempotent(self) -> None:
        secret = "secrettoken" + "123"
        s = f"Authorization: Bearer {secret}"
        once = redact_text(s)
        twice = redact_text(once)
        self.assertNotIn(secret, once)
        self.assertEqual(twice, once)

    def test_keeps_non_secret_text(self) -> None:
        self.assertEqual(redact_text("hello world"), "hello world")

    def test_redacts_nested_mapping_values(self) -> None:
        out = redact_mapping({"a": {"api_key": "ghp_ABCDEFGHIJKLMNOPQRST"}, "b": "ok"})
        assert isinstance(out, dict)  # narrow object -> dict for the type checker
        inner = out["a"]
        assert isinstance(inner, dict)
        self.assertNotIn("ghp_ABCDEFGHIJKLMNOPQRST", str(inner["api_key"]))
        self.assertEqual(out["b"], "ok")

    def test_does_not_mutate_input(self) -> None:
        src = {"k": "ghp_ABCDEFGHIJKLMNOPQRST"}
        redact_mapping(src)
        self.assertEqual(src["k"], "ghp_ABCDEFGHIJKLMNOPQRST")  # original untouched


if __name__ == "__main__":
    unittest.main()
