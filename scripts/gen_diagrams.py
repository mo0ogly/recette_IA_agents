#!/usr/bin/env python3
"""Inject / check the mermaid diagrams of docs/ARCHITECTURE.md.

The diagram bodies live in scripts/diagrams/architecture.py (one function per
diagram). The markdown carries one marker per block:

    <!-- mermaid:NAME (generated: scripts/diagrams/architecture.py) -->
    ```mermaid
    ...body...
    ```

Modes:
    --write    rewrite each marked block from its Python source
    --check    exit 1 if the markdown drifted from the Python source (default)
    --render   render every diagram with mmdc (skipped if mmdc is absent)
    --list     list diagram names

Stdlib only. Used by the doc-librarian workflow to keep diagrams editable.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "docs" / "ARCHITECTURE.md"
# English mirror of the same document (Docusaurus i18n). Generated from the SAME
# Python source via the fr->en label map, so the .py stays authoritative for
# both locales (no hand-editing generated mermaid).
EN_DOC = (
    REPO_ROOT
    / "docs-site"
    / "i18n"
    / "en"
    / "docusaurus-plugin-content-docs"
    / "current"
    / "ARCHITECTURE.md"
)
MARKER = re.compile(
    r"<!-- mermaid:(?P<name>[a-z0-9-]+) \(generated: [^)]+\) -->\n```mermaid\n(?P<body>.*?)```",
    re.S,
)

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from diagrams.architecture import DIAGRAMS  # noqa: E402
from diagrams.architecture_i18n import translate as _translate_en  # noqa: E402


def _bodies(locale: str) -> dict[str, str]:
    """Diagram bodies for a locale: 'fr' = source, 'en' = label-translated."""
    if locale == "en":
        return {name: _translate_en(body) for name, body in DIAGRAMS.items()}
    return dict(DIAGRAMS)


def _sub_block(text: str, name: str, body: str) -> tuple[str, bool]:
    """Replace the marked block `name` with `body`; return (text, found)."""
    found = False

    def repl(match: re.Match) -> str:
        nonlocal found
        if match.group("name") != name:
            return match.group(0)
        found = True
        head = match.group(0).split("```mermaid", 1)[0]
        return f"{head}```mermaid\n{body.rstrip()}\n```"

    return MARKER.sub(repl, text), found


def _write_doc(doc: Path, bodies: dict[str, str]) -> int:
    if not doc.exists():
        print(f"SKIP (absent): {doc}")
        return 0
    text = doc.read_text(encoding="utf-8")
    for name, body in bodies.items():
        text, found = _sub_block(text, name, body)
        if not found:
            print(f"ERROR: marker 'mermaid:{name}' not found in {doc}")
            return 1
    doc.write_text(text, encoding="utf-8")
    print(f"wrote {len(bodies)} diagrams into {doc}")
    return 0


def _check_doc(doc: Path, bodies: dict[str, str], src_hint: str) -> int:
    if not doc.exists():
        print(f"SKIP (absent): {doc}")
        return 0
    text = doc.read_text(encoding="utf-8")
    in_doc = {m.group("name"): m.group("body").rstrip() for m in MARKER.finditer(text)}
    status = 0
    for name, body in bodies.items():
        if name not in in_doc:
            print(f"MISSING in {doc.name}: {name}")
            status = 1
        elif in_doc[name] != body.rstrip():
            print(f"DRIFT: {name} ({doc.name} differs from {src_hint})")
            status = 1
    for name in in_doc:
        if name not in bodies:
            print(f"UNKNOWN marker in {doc.name} (no python source): {name}")
            status = 1
    return status


def cmd_write() -> int:
    rc = _write_doc(DOC, _bodies("fr"))
    rc |= _write_doc(EN_DOC, _bodies("en"))
    return rc


def cmd_check() -> int:
    rc = _check_doc(DOC, _bodies("fr"), "scripts/diagrams/architecture.py")
    rc |= _check_doc(EN_DOC, _bodies("en"), "architecture.py + architecture_i18n.py (en map)")
    if rc == 0:
        print(f"in sync: {len(DIAGRAMS)} diagrams x 2 locales (fr, en)")
    return rc


def cmd_render() -> int:
    mmdc = shutil.which("mmdc")
    if mmdc is None:
        print("mmdc not installed; skipping render validation")
        return 0
    status = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in DIAGRAMS.items():
            src = Path(tmp) / f"{name}.mmd"
            src.write_text(body, encoding="utf-8")
            proc = subprocess.run(
                [mmdc, "-i", str(src), "-o", str(src.with_suffix(".svg")), "--quiet"],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print(f"RENDER FAIL: {name}\n{proc.stderr.strip()[:400]}")
                status = 1
            else:
                print(f"render ok: {name}")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for name in DIAGRAMS:
            print(name)
        return 0
    if args.write:
        return cmd_write()
    if args.render:
        return cmd_render()
    return cmd_check()


if __name__ == "__main__":
    raise SystemExit(main())
