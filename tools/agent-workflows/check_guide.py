#!/usr/bin/env python3
"""Check the bounded, repository-local agent field guide (stdlib only)."""

import re
import sys
from pathlib import Path


def check(root):
    root = Path(root).resolve()
    index = root / "index.md"
    errors = []
    if not index.is_file():
        return ["missing index.md"]
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            errors.append(f"{path.name}: symbolic links are not portable")
            continue
        if not path.is_file():
            continue
        if path.suffix != ".md":
            errors.append(f"{path.name}: only Markdown notes are supported")
            continue
        content = path.read_text(encoding="utf-8")
        count = len(content.splitlines())
        total += count
        limit = 120 if path == index else 200
        if count > limit:
            errors.append(f"{path.name}: {count} lines exceeds {limit}")
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            if "://" in link or link.startswith("#"):
                continue
            target = (path.parent / link.split("#")[0]).resolve()
            # Notes may cite files elsewhere in the repository, but not outside it.
            repo = root.parent.parent
            if not target.is_relative_to(repo) or not target.is_file():
                errors.append(f"{path.name}: missing or external local link: {link}")
    if total > 1200:
        errors.append(f"guide: {total} lines exceeds 1200")
    return errors


if __name__ == "__main__":
    guide = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".claude/field-guide")
    problems = check(guide)
    print("\n".join(problems) if problems else "Field guide: PASS")
    sys.exit(bool(problems))
