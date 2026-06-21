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
