"""Tests for the pattern and scan layers."""

from __future__ import annotations

from pathlib import Path

from python_recette import patterns, scan
from python_recette.model import Verdict


def test_detects_print_and_sql_injection(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text(
        'def h(x):\n    print(x)\n    cur.execute(f"SELECT * FROM t WHERE id = {x}")\n',
        encoding="utf-8",
    )
    results = {r.id: r for r in patterns.run_all([bad], tmp_path)}
    assert results["A1"].verdict is Verdict.FAIL  # print()
    assert results["B1"].verdict is Verdict.FAIL  # SQL injection via f-string


def test_clean_file_passes_core_checks(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    good.write_text(
        '"""Doc."""\n\n\ndef add(a: int, b: int) -> int:\n    """Add."""\n    return a + b\n',
        encoding="utf-8",
    )
    results = {r.id: r for r in patterns.run_all([good], tmp_path)}
    assert results["A1"].verdict is Verdict.PASS
    assert results["B1"].verdict is Verdict.PASS
    assert results["B6"].verdict is Verdict.PASS


def test_test_lines_excludes_test_functions() -> None:
    src = "def real():\n    print(1)\n\n\ndef test_it():\n    assert real() is None\n"
    flags = scan.test_lines(src)
    assert flags[0] is False  # real() header
    assert flags[4] is True  # test_it header
    assert flags[5] is True  # body of test
