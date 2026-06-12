"""Drift gate: docs/ARCHITECTURE.md mermaid blocks match their Python source.

The diagrams of the foundational architecture document are generated from
scripts/diagrams/architecture.py (see scripts/gen_diagrams.py). This test
fails when someone edits a mermaid block in the markdown by hand instead of
editing the Python source and re-running --write.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "docs" / "ARCHITECTURE.md"
MARKER = re.compile(
    r"<!-- mermaid:(?P<name>[a-z0-9-]+) \(generated: [^)]+\) -->\n```mermaid\n(?P<body>.*?)```",
    re.S,
)

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from diagrams.architecture import DIAGRAMS  # noqa: E402


class TestDiagramsSync(unittest.TestCase):
    def setUp(self) -> None:
        self.in_doc = {
            m.group("name"): m.group("body").rstrip()
            for m in MARKER.finditer(DOC.read_text(encoding="utf-8"))
        }

    def test_every_python_diagram_is_in_the_markdown(self) -> None:
        missing = sorted(set(DIAGRAMS) - set(self.in_doc))
        self.assertEqual(missing, [], f"diagrams missing from {DOC.name}: {missing}")

    def test_every_markdown_block_has_a_python_source(self) -> None:
        unknown = sorted(set(self.in_doc) - set(DIAGRAMS))
        self.assertEqual(unknown, [], f"markdown blocks without python source: {unknown}")

    def test_no_drift_between_markdown_and_python(self) -> None:
        for name, body in DIAGRAMS.items():
            with self.subTest(diagram=name):
                self.assertEqual(
                    self.in_doc.get(name),
                    body.rstrip(),
                    f"'{name}' drifted: edit scripts/diagrams/architecture.py then "
                    "run 'python3 scripts/gen_diagrams.py --write'",
                )

    def test_every_mermaid_block_is_marked(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        fences = len(re.findall(r"```mermaid\n", text))
        self.assertEqual(
            fences,
            len(self.in_doc),
            "a mermaid block without a '<!-- mermaid:NAME -->' marker was added; "
            "add it to scripts/diagrams/architecture.py instead",
        )


if __name__ == "__main__":
    unittest.main()
