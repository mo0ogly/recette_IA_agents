"""Stdlib .env loader: parsing + override precedence (env wins over file)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from recette.api._dotenv import load_dotenv, parse_env


class ParseEnvTests(unittest.TestCase):
    def test_parses_pairs_skips_comments_blanks_and_malformed(self) -> None:
        parsed = parse_env("# comment\nGROQ_API_KEY=abc\n\nbad line\nEMPTY=\n")
        self.assertEqual(parsed, {"GROQ_API_KEY": "abc", "EMPTY": ""})

    def test_strips_matching_surrounding_quotes(self) -> None:
        self.assertEqual(parse_env('A="x y"\nB=\'z\''), {"A": "x y", "B": "z"})


class LoadDotenvTests(unittest.TestCase):
    def test_missing_file_is_noop(self) -> None:
        self.assertEqual(load_dotenv(Path("/no/such/.env")), [])

    def test_loads_and_env_var_wins_over_file(self) -> None:
        os.environ.pop("AGENTRAIL_DOTENV_NEW", None)
        os.environ["AGENTRAIL_DOTENV_KEEP"] = "from-env"
        self.addCleanup(lambda: os.environ.pop("AGENTRAIL_DOTENV_NEW", None))
        self.addCleanup(lambda: os.environ.pop("AGENTRAIL_DOTENV_KEEP", None))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("AGENTRAIL_DOTENV_NEW=from-file\nAGENTRAIL_DOTENV_KEEP=from-file\n")
            applied = load_dotenv(path)
        self.assertEqual(os.environ["AGENTRAIL_DOTENV_NEW"], "from-file")
        self.assertEqual(os.environ["AGENTRAIL_DOTENV_KEEP"], "from-env")
        self.assertEqual(applied, ["AGENTRAIL_DOTENV_NEW"])

    def test_override_true_replaces_existing(self) -> None:
        os.environ["AGENTRAIL_DOTENV_OV"] = "old"
        self.addCleanup(lambda: os.environ.pop("AGENTRAIL_DOTENV_OV", None))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("AGENTRAIL_DOTENV_OV=new\n")
            load_dotenv(path, override=True)
        self.assertEqual(os.environ["AGENTRAIL_DOTENV_OV"], "new")


if __name__ == "__main__":
    unittest.main()
