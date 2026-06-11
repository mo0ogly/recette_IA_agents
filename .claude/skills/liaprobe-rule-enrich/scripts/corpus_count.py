#!/usr/bin/env python3
"""corpus_count -- distinguish REAL LiaProbe rules from nested metadata.

Why this exists (RETEX wave 6, 2026-05-29): a recursive `find <dir> -name '*.json'`
over a patterns directory inflates the count with capture-metadata
(captures/*/analysis|study verdict.json, study.json -- NOT rules, zero matchers),
gitignored `todo/` scratch, and `_generated_onyphe/` study extracts. Example:
banner-signatures reported 5052 recursive but only 1713 are real rules.

The enrichment orchestrator (run_enrich.py `_enumerate_rules`) already scans
top-level only (`dir.glob('*.json')`), so it never over-counts. This helper makes
the same distinction explicit for humans BEFORE chasing a phantom number, and is
reusable across every patterns dir (tcp-probes, web-signatures, service-detectors).

Usage:
    python3 corpus_count.py /opt/lia-sec/liaprobe/patterns/banner-signatures
    python3 corpus_count.py /opt/lia-sec/liaprobe/patterns/banner-signatures --json

Output (text):
    real=1713 phantom=3339 total_recursive=5052
      captures/        2589
      todo/             694
      _generated_onyphe/ 56

`real` = top-level *.json (what the engine loads and what enrichment iterates).
`phantom` = everything nested under a subdirectory (metadata, scratch, extracts).
Exit 0 always (this is a reporting tool, not a gate).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def count_corpus(patterns_dir: Path) -> dict:
    """Return real (top-level) vs phantom (nested) rule-file counts.

    real         : number of *.json directly in patterns_dir
    phantom      : number of *.json under any subdirectory
    by_subdir    : phantom count keyed by the first path component under the dir
    total_recursive : real + phantom (the misleading `find` number)
    """
    d = patterns_dir.resolve()
    if not d.exists() or not d.is_dir():
        raise SystemExit(f"not a directory: {d}")

    real_files = sorted(p for p in d.glob("*.json") if p.is_file())
    all_files = [p for p in d.rglob("*.json") if p.is_file()]

    real = len(real_files)
    by_subdir: Counter[str] = Counter()
    phantom = 0
    for p in all_files:
        rel = p.relative_to(d)
        if len(rel.parts) == 1:
            continue  # top-level, already counted as real
        phantom += 1
        by_subdir[rel.parts[0]] += 1

    return {
        "patterns_dir": str(d),
        "real": real,
        "phantom": phantom,
        "total_recursive": real + phantom,
        "by_subdir": dict(by_subdir.most_common()),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="corpus_count",
        description="Real (top-level) vs phantom (nested metadata) LiaProbe rule counts.",
    )
    p.add_argument("patterns_dir", type=Path, help="A patterns/<tier> directory")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = p.parse_args(argv)

    result = count_corpus(args.patterns_dir)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(
        f"real={result['real']} phantom={result['phantom']} "
        f"total_recursive={result['total_recursive']}"
    )
    for sub, n in result["by_subdir"].items():
        print(f"  {sub + '/':20} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
