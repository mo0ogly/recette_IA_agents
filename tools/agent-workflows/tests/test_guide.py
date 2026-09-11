import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("guide", Path(__file__).parents[1] / "check_guide.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GuideTests(unittest.TestCase):
    def test_budget_and_missing_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".claude/field-guide"
            root.mkdir(parents=True)
            (root / "index.md").write_text("[Useful note](note.md)\n")
            self.assertTrue(module.check(root))
            (root / "note.md").write_text("Verified observation\n")
            self.assertEqual(module.check(root), [])
            (root / "index.md").write_text("x\n" * 121)
            self.assertTrue(module.check(root))

    def test_total_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".claude/field-guide"
            root.mkdir(parents=True)
            (root / "index.md").write_text("Index\n")
            for i in range(6):
                (root / f"note{i}.md").write_text("x\n" * 200)
            self.assertTrue(module.check(root))

    def test_external_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".claude/field-guide"
            root.mkdir(parents=True)
            (root / "index.md").write_text("[Bad](../../../../etc/passwd)\n")
            self.assertTrue(module.check(root))
