"""File collection and test-region detection for Python sources."""

from __future__ import annotations

from pathlib import Path


def collect_py_files(path: Path) -> list[Path]:
    """Collect every ``.py`` file under ``path`` (or ``path`` itself if a file).

    Skips virtualenvs, caches and build dirs.
    """
    skip = {".venv", ".venv-pyaudit", "venv", "__pycache__", ".git", "build", "dist", ".mypy_cache"}
    if path.is_file():
        return [path] if path.suffix == ".py" else []
    files = [p for p in path.rglob("*.py") if not any(part in skip for part in p.parts)]
    return sorted(files)


def is_test_path(p: Path) -> bool:
    """True if the path is conventionally test-only."""
    name = p.name
    return "tests" in p.parts or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def nearest_project_dir(path: Path) -> Path:
    """Find the nearest ancestor containing a project/lock marker.

    Used as the working directory for the static tools. Falls back to ``path``
    (or its parent if a file).
    """
    markers = ("pyproject.toml", "setup.py", "requirements.txt", "uv.lock", "poetry.lock")
    start = path.parent if path.is_file() else path
    for directory in (start, *start.parents):
        if any((directory / m).is_file() for m in markers):
            return directory
    return start


def read_file(p: Path) -> str | None:
    """Read a file, returning ``None`` (with a warning) on error."""
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # pragma: no cover - rare I/O path
        import sys

        print(f"python_recette: skipping {p} ({exc})", file=sys.stderr)
        return None


def test_lines(content: str) -> list[bool]:
    """Per-line flag: is this line inside a test function/class?

    Heuristic: indentation tracking. A ``def test_`` / ``class Test`` header opens
    a region that ends when indentation returns to the header's level or less.
    """
    flags: list[bool] = []
    region_indent: int | None = None
    for raw in content.splitlines():
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped)
        if region_indent is not None and stripped and indent <= region_indent:
            region_indent = None
        is_header = stripped.startswith(("def test_", "async def test_", "class Test"))
        if is_header and region_indent is None:
            region_indent = indent
            flags.append(True)
            continue
        flags.append(region_indent is not None)
    return flags
