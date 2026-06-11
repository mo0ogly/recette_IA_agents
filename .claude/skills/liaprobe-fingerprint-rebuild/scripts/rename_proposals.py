#!/usr/bin/env python3
# Dry-run filename canonicalization for LiaProbe rule JSONs.
# Implements the canonical naming rule defined in
# .claude/skills/liaprobe-fingerprint-rebuild/SKILL.md (section "Canonical
# filename rule"). Single source: NVD CPE vendor + product.
#
#   Tier 1a: _meta_enrichment.canonical_vendor.{vendor_name, product_name_db}
#            when bucket = CONFIDENT and not ambiguous
#   Tier 1b: bare top-level vendor + product strings (only with
#            --include-non-canonical flag)
#   SKIP: vendor in {Various, Unknown, Generic, Multiple, N/A, ""}
#
# This script DOES NOT rename files. It emits a JSON proposal artifact
# for human review. The follow-up cycle (c25+) will apply selected
# renames with `git mv`.
#
# Usage:
#   ./rename_proposals.py [--liaprobe-root <path>] [--out <file>]
#                         [--include-non-canonical]
#                         [--rules-subdir <path>] [--recurse]
#                         [--quiet]
#
# Default behaviour:
#   - scans <liaprobe-root>/patterns/lia/*.json
#   - reads _meta_enrichment.canonical_vendor when present (Tier 1a)
#   - falls back to bare vendor + product fields with --include-non-canonical
#   - skips rules with vendor == "Various" / "Unknown" / missing
#   - emits JSON artifact (schema lia-rename-proposals-v1)
#   - detects collisions (two rules emitting same proposed_basename)
#   - emits field_updates block per proposal (vendor + product + source.file)
#
# Exit codes: 0 OK, 2 fatal env error (no rules dir).

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

SCHEMA = "lia-rename-proposals-v1"
SCHEMA_VERSION = 1
DEFAULT_LIAPROBE_ROOT = Path("/opt/lia-sec/liaprobe")
DEFAULT_OUT = Path(
    "/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild"
) / f"RENAME_PROPOSALS_{_dt.date.today().isoformat()}.json"

# Vendor / product strings that block proposal generation. Lower-cased match.
UNRESOLVABLE_VENDORS = {
    "various",
    "unknown",
    "n/a",
    "",
    "generic",
    "multiple",
}

# Sanitize a vendor or product name into a filename-safe token.
# Rules:
#   - Strip leading/trailing whitespace
#   - Title-case each whitespace-separated word (so "http server" ->
#     "Http_Server", matching the _meta_enrichment.canonical_vendor
#     convention used since c10)
#   - Replace any non [A-Za-z0-9._-] char with '_'
#   - Collapse repeated underscores
_BAD_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MULTI_UNDERSCORE = re.compile(r"_{2,}")


def _sanitize(part: str) -> str:
    s = (part or "").strip()
    if not s:
        return ""
    # Words may already be canonical "Http_Server". Re-titlecase only
    # if the input has any lowercase word boundary.
    pieces = re.split(r"[\s_]+", s)
    titled = "_".join(p[:1].upper() + p[1:] if p else "" for p in pieces if p)
    titled = _BAD_CHARS.sub("_", titled)
    titled = _MULTI_UNDERSCORE.sub("_", titled).strip("_.")
    return titled


def _preserve_brand_caps(canonical: str, bare: Optional[str]) -> str:
    # PG `product_name_db` is the normalized canonical form (often
    # lowercase except first letter, e.g. "Wireguard"). The top-level
    # `vendor`/`product` field in the rule JSON often carries the
    # brand-correct capitalization (e.g. "WireGuard", "MariaDB").
    #
    # Two recovery paths:
    #   (1) Full match: bare and canonical equal case-insensitively
    #       but differ in caps -> use bare (preserves WireGuard).
    #   (2) Token match: bare is a verbose label ("MariaDB Foundation")
    #       and one of its space/underscore-separated tokens matches
    #       canonical case-insensitively -> use that token (preserves
    #       MariaDB while dropping " Foundation").
    # Otherwise the canonical wins because the bare is a verbose
    # non-normalized label ("Apache HTTP Server" -> "Http_Server").
    if not bare:
        return canonical
    canon_token = _sanitize(canonical)
    bare_token = _sanitize(bare)
    if canon_token.lower() == bare_token.lower() and canon_token != bare_token:
        return bare_token
    canon_lower = canon_token.lower()
    for piece in re.split(r"[\s_]+", bare):
        piece = piece.strip()
        if piece and piece.lower() == canon_lower and piece != canon_token:
            return piece
    return canonical


def _extract_canonical(rule: dict[str, Any]) -> Optional[dict[str, Any]]:
    meta = rule.get("_meta_enrichment") or {}
    cv = meta.get("canonical_vendor") or {}
    vendor_raw = cv.get("vendor_name")
    product_raw = cv.get("product_name_db")
    if not vendor_raw or not product_raw:
        return None
    bucket = (cv.get("bucket") or "").upper()
    ambiguous = bool(cv.get("ambiguous"))
    confident = bucket == "CONFIDENT" and not ambiguous
    chain = cv.get("alias_chain") or []
    chain_hash = hashlib.sha256(
        json.dumps(chain, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    # Preserve brand caps from top-level fields when the canonical
    # form is just a normalization of the same string (case-insensitive
    # match). Otherwise trust the canonical.
    vendor = _preserve_brand_caps(vendor_raw, rule.get("vendor"))
    product = _preserve_brand_caps(product_raw, rule.get("product"))
    return {
        "tier": "1a_canonical_vendor",
        "vendor": vendor,
        "product": product,
        "vendor_canonical_raw": vendor_raw,
        "product_canonical_raw": product_raw,
        "bucket": bucket,
        "ambiguous": ambiguous,
        "confident": confident,
        "resolved_via": cv.get("resolved_via"),
        "vendor_id": cv.get("vendor_id"),
        "product_id": cv.get("product_id"),
        "alias_chain_hash": chain_hash,
    }


def _extract_bare(rule: dict[str, Any]) -> Optional[dict[str, Any]]:
    vendor = rule.get("vendor") or ""
    product = rule.get("product") or ""
    if not vendor or not product:
        return None
    if vendor.strip().lower() in UNRESOLVABLE_VENDORS:
        return None
    return {
        "tier": "1b_bare_fields",
        "vendor": vendor,
        "product": product,
        "bucket": None,
        "ambiguous": None,
        "confident": False,  # bare fields = lower trust
        "resolved_via": "bare_vendor_product_fallback",
        "vendor_id": None,
        "product_id": None,
        "alias_chain_hash": None,
    }


def _propose_filename(vendor: str, product: str) -> str:
    v = _sanitize(vendor)
    p = _sanitize(product)
    if not p:
        return ""
    if not v:
        return f"{p}.json"
    if v.lower() == p.lower():
        return f"{p}.json"
    return f"{v}_{p}.json"


def _scan_rules(rules_dir: Path, recurse: bool = False) -> list[Path]:
    pattern = "**/*.json" if recurse else "*.json"
    out: list[Path] = []
    for p in rules_dir.glob(pattern):
        if not p.is_file():
            continue
        # Skip subdirs that hold transient data (todo, captures, archive)
        if any(part in {"todo", "captures", "archive", "_archive"} for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


def _build_proposal(
    rule_path: Path,
    rule: dict[str, Any],
    include_non_canonical: bool,
) -> Optional[dict[str, Any]]:
    canonical = _extract_canonical(rule)
    if canonical:
        src = canonical
    else:
        bare = _extract_bare(rule)
        if bare is None:
            return {
                "rule_file": str(rule_path),
                "rule_id": rule.get("id"),
                "current_basename": rule_path.name,
                "proposed_basename": None,
                "action": "skip_unresolvable",
                "reason": "no _meta_enrichment.canonical_vendor and no bare vendor/product",
                "tier": None,
                "evidence": {},
                "flags": [],
            }
        if not include_non_canonical:
            return {
                "rule_file": str(rule_path),
                "rule_id": rule.get("id"),
                "current_basename": rule_path.name,
                "proposed_basename": None,
                "action": "skip_non_canonical",
                "reason": "no canonical_vendor; bare fallback not included by default (use --include-non-canonical)",
                "tier": "1b_bare_fields",
                "evidence": {"bare_vendor": rule.get("vendor"), "bare_product": rule.get("product")},
                "flags": [],
            }
        src = bare

    proposed = _propose_filename(src["vendor"], src["product"])
    if not proposed:
        return {
            "rule_file": str(rule_path),
            "rule_id": rule.get("id"),
            "current_basename": rule_path.name,
            "proposed_basename": None,
            "action": "skip_empty_product",
            "reason": "sanitized product is empty",
            "tier": src["tier"],
            "evidence": src,
            "flags": [],
        }

    flags: list[str] = []
    if not src["confident"]:
        flags.append("not_confident_resolution")
    if src.get("ambiguous"):
        flags.append("canonical_marked_ambiguous")

    same_name = proposed == rule_path.name

    # In-JSON field synchronization: ONLY source.file is patched on
    # rename. Top-level vendor + product fields are NEVER touched
    # because the engine uses them as the detected_product label for
    # ground-truth comparison (Onyphe verdict). Normalizing them to
    # PG canonical form (e.g. "Apache HTTP Server" -> "Http_Server")
    # breaks 1658 verdict CORRECT -> WRONG (incident c25 ST3 2026-05-13).
    # The canonical values already live in _meta_enrichment.canonical_vendor
    # (sole source of truth for naming). User mandate "le nom du produit
    # et du vendor doit etre aussi dans le json" is satisfied by that
    # block being part of the rule body.
    field_updates: dict[str, dict[str, Any]] = {}
    current_source_file = ((rule.get("source") or {}).get("file"))
    if not same_name and current_source_file != proposed:
        field_updates["source.file"] = {"current": current_source_file, "proposed": proposed}

    if same_name and not field_updates:
        action = "already_canonical"
    elif same_name and field_updates:
        action = "fields_only_update"
    else:
        action = "rename"

    return {
        "rule_file": str(rule_path),
        "rule_id": rule.get("id"),
        "current_basename": rule_path.name,
        "proposed_basename": proposed,
        "action": action,
        "tier": src["tier"],
        "evidence": {
            "vendor_used": src["vendor"],
            "product_used": src["product"],
            "bucket": src["bucket"],
            "ambiguous": src["ambiguous"],
            "resolved_via": src["resolved_via"],
            "vendor_id": src["vendor_id"],
            "product_id": src["product_id"],
            "alias_chain_hash": src["alias_chain_hash"],
        },
        "field_updates": field_updates,
        "flags": flags,
    }


def _detect_collisions(proposals: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_target: dict[str, list[str]] = defaultdict(list)
    for p in proposals:
        target = p.get("proposed_basename")
        if not target or p.get("action") not in ("rename", "already_canonical"):
            continue
        by_target[target].append(p["rule_file"])
    return {k: v for k, v in by_target.items() if len(v) > 1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--liaprobe-root", type=Path, default=DEFAULT_LIAPROBE_ROOT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--include-non-canonical", action="store_true",
                    help="Generate proposals for rules without _meta_enrichment.canonical_vendor (uses bare vendor/product)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--rules-subdir", default="patterns/lia",
                    help="Sub-path under --liaprobe-root to scan (default: patterns/lia)")
    ap.add_argument("--recurse", action="store_true",
                    help="Recursively scan subdirectories (excludes todo/captures/archive/_archive)")
    args = ap.parse_args()

    rules_dir = args.liaprobe_root / args.rules_subdir
    if not rules_dir.is_dir():
        print(f"FATAL: rules dir not found: {rules_dir}", file=sys.stderr)
        return 2

    rule_paths = _scan_rules(rules_dir, recurse=args.recurse)
    proposals: list[dict[str, Any]] = []
    for rp in rule_paths:
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            proposals.append({
                "rule_file": str(rp),
                "rule_id": None,
                "current_basename": rp.name,
                "proposed_basename": None,
                "action": "skip_parse_error",
                "reason": str(exc),
                "tier": None,
                "evidence": {},
                "flags": ["parse_error"],
            })
            continue
        prop = _build_proposal(rp, data, args.include_non_canonical)
        if prop is not None:
            proposals.append(prop)

    collisions = _detect_collisions(proposals)
    # Annotate colliding proposals
    for p in proposals:
        target = p.get("proposed_basename")
        if target and target in collisions and p.get("action") == "rename":
            p["flags"].append("collision_with_other_rule")

    actions = Counter(p["action"] for p in proposals)
    flag_counts: Counter = Counter()
    for p in proposals:
        for f in p.get("flags", []):
            flag_counts[f.split(":", 1)[0]] += 1

    artifact = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "generator": "rename_proposals.py (apex c24)",
        "rule": "SKILL.md 'Canonical filename rule' -- NVD CPE vendor + product only",
        "inputs": {
            "liaprobe_root": str(args.liaprobe_root),
            "rules_dir": str(rules_dir),
            "rules_scanned": len(rule_paths),
            "include_non_canonical": args.include_non_canonical,
        },
        "summary": {
            "total_proposals": len(proposals),
            "by_action": dict(actions),
            "by_flag": dict(flag_counts),
            "collisions": len(collisions),
        },
        "collisions": collisions,
        "proposals": proposals,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    if not args.quiet:
        print(f"rules scanned          : {len(rule_paths)}")
        print(f"proposals emitted      : {len(proposals)}")
        for k, v in sorted(actions.items()):
            print(f"  action {k:<26}: {v}")
        for k, v in sorted(flag_counts.items()):
            print(f"  flag   {k:<26}: {v}")
        print(f"name collisions        : {len(collisions)}")
        print(f"output                 : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
