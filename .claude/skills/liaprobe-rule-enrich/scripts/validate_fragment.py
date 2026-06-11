#!/usr/bin/env python3
"""validate_fragment.py -- Strict JSONSchema validation for cycle 9 cert pattern fragments.

R-LiaProbeEnrich-v2 enforcement: every fragment produced by parallel agents MUST
match the canonical schema. Refuses anything else. Empties the 5-style schema
variant overhead introduced Phase 1-4.

Usage:
  python3 validate_fragment.py <fragment.json>           # single file
  python3 validate_fragment.py <fragments_dir>           # all *.json in dir
  python3 validate_fragment.py --strict <path>           # exit 1 on first error
  python3 validate_fragment.py --report <path>           # full report (default)

Exit codes:
  0 = all fragments valid
  1 = at least one fragment invalid
  2 = usage error / schema not found
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: jsonschema not installed. apt install python3-jsonschema", file=sys.stderr)
    sys.exit(2)

SCHEMA_PATH = Path("/opt/lia-sec/dev/_alire/tracking/liaprobe-enrich-v2/schemas/cert_pattern_fragment.schema.json")


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    if not path.exists():
        print(f"ERROR: schema not found at {path}", file=sys.stderr)
        sys.exit(2)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_one(frag_path: Path, validator: Draft202012Validator) -> tuple[bool, list[str]]:
    """Return (ok, errors_list). errors_list is human-readable strings."""
    try:
        data = json.loads(frag_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, [f"JSON parse error: {e}"]
    except OSError as e:
        return False, [f"cannot read: {e}"]

    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if not errors:
        return True, []

    msgs = []
    for e in errors:
        loc = ".".join(str(p) for p in e.absolute_path) or "<root>"
        msgs.append(f"  [{loc}] {e.message}")
    return False, msgs


def cross_check(fragment: dict, frag_path: Path) -> list[str]:
    """Cross-validation beyond JSONSchema:
    - every pattern_id referenced in products[].patterns must exist in pattern_definitions
    - every pattern_id in pattern_definitions should be referenced by at least 1 product
    """
    errors = []
    pdefs = set(fragment.get("pattern_definitions", {}).keys())
    referenced = set()
    for prod_key, prod in fragment.get("products", {}).items():
        for pid in prod.get("patterns", []):
            referenced.add(pid)
            if pid not in pdefs:
                errors.append(
                    f"  [products.{prod_key}.patterns] pattern_id '{pid}' "
                    f"not defined in pattern_definitions"
                )
    orphan = pdefs - referenced
    if orphan:
        errors.append(
            f"  orphan pattern_definitions (no product references them): {sorted(orphan)}"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="fragment.json or directory of fragments")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH,
                        help="override schema path")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 on first invalid fragment (default: continue, summary)")
    parser.add_argument("-q", "--quiet", action="store_true", help="quiet mode (only errors)")
    args = parser.parse_args(argv)

    schema = load_schema(args.schema)
    validator = Draft202012Validator(schema)

    if args.path.is_file():
        files = [args.path]
    elif args.path.is_dir():
        files = sorted(args.path.glob("*.json"))
        if not files:
            print(f"no .json fragments in {args.path}", file=sys.stderr)
            return 2
    else:
        print(f"path not found: {args.path}", file=sys.stderr)
        return 2

    ok_count = 0
    fail_count = 0
    for f in files:
        ok, errs = validate_one(f, validator)
        if ok:
            try:
                fragment = json.loads(f.read_text(encoding="utf-8"))
                cross_errs = cross_check(fragment, f)
            except (json.JSONDecodeError, OSError):
                cross_errs = []
            if cross_errs:
                ok = False
                errs.extend(cross_errs)
        if ok:
            ok_count += 1
            if not args.quiet:
                print(f"OK     {f.name}")
        else:
            fail_count += 1
            print(f"FAIL   {f.name}")
            for e in errs:
                print(e)
            if args.strict:
                return 1

    print(f"\nSummary: {ok_count} OK, {fail_count} FAIL ({len(files)} total)")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
