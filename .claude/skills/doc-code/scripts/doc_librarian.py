#!/usr/bin/env python3
"""
LIA-SEC Documentation Librarian v1.0
Author: mo0ogly@proton.me
License: Proprietary - LIA-Security

Automated documentation health: organization, versioning, obsolescence
detection, indexation, and naming clarity.

Commands:
    audit     - Full audit of docs/ (organization, naming, metadata, staleness)
    organize  - Move misplaced files to correct type directories
    rename    - Rename files to match naming convention {module}_{type}_en.md
    freshness - Check doc freshness against git history (detect stale docs)
    reindex   - Regenerate INDEX.md with full catalog
    fix       - Auto-fix all issues found by audit (interactive by default)

Usage:
    python3 doc_librarian.py audit docs/
    python3 doc_librarian.py organize docs/ [--dry-run]
    python3 doc_librarian.py rename docs/ [--dry-run]
    python3 doc_librarian.py freshness docs/ [--max-age=90]
    python3 doc_librarian.py reindex docs/ -o docs/INDEX.md
    python3 doc_librarian.py fix docs/ [--dry-run] [--auto]

Exit codes: 0 = healthy, 1 = issues found, 2 = critical issues
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOC_TYPES = {
    "TECH": "Technical Documentation",
    "API":  "API Reference",
    "ARCH": "Architecture Document",
    "USER": "User Guide",
    "SEC":  "Security Documentation",
    "SPEC": "Functional Specification",
}

TYPE_TO_DIR = {
    "API":  "api",
    "ARCH": "architecture",
    "TECH": "technical",
    "USER": "user-guides",
    "SEC":  "security",
    "SPEC": "specs",
}

DIR_TO_TYPE = {v: k for k, v in TYPE_TO_DIR.items()}

NAMING_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*_(api|arch|tech|user|sec|spec)_en\.md$"
)

ARCHIVE_DIR = "archive"
DIAGRAMS_DIR = "diagrams"
EXPORTS_DIR = "exports"

CLASSIFIER_SCRIPT = Path(__file__).parent / "doc_classifier.py"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _meta_path(doc_path: Path) -> Path:
    """Sidecar metadata path for a document."""
    return doc_path.parent / f".{doc_path.stem}.doc-meta.json"


def _load_meta(doc_path: Path) -> dict | None:
    """Load metadata if it exists."""
    mp = _meta_path(doc_path)
    if not mp.exists():
        return None
    with open(mp, encoding="utf-8") as f:
        return json.load(f)


def _save_meta(doc_path: Path, meta: dict) -> None:
    """Save metadata sidecar."""
    mp = _meta_path(doc_path)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _find_docs(base: Path) -> list[Path]:
    """Find all .md documentation files (excluding INDEX, archive, and dotfiles)."""
    docs = []
    for md in sorted(base.rglob("*.md")):
        rel = md.relative_to(base)
        parts = rel.parts
        # Skip archive, node_modules, .venv, hidden dirs
        if any(p.startswith(".") or p in (ARCHIVE_DIR, "node_modules", ".venv") for p in parts):
            continue
        if md.name in ("INDEX.md", "README.md"):
            continue
        # Skip RECETTE files
        if md.name.startswith("RECETTE_"):
            continue
        docs.append(md)
    return docs


def _find_metas(base: Path) -> list[Path]:
    """Find all .doc-meta.json files."""
    return sorted(base.rglob(".*.doc-meta.json"))


def _git_last_modified(file_path: Path) -> str | None:
    """Get the last git modification date for a file."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", str(file_path)],
            capture_output=True, text=True, timeout=10, cwd=file_path.parent
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()[:10]  # YYYY-MM-DD
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _infer_type_from_dir(doc_path: Path, base: Path) -> str | None:
    """Infer doc type from its parent directory."""
    rel = doc_path.relative_to(base)
    if len(rel.parts) >= 2:
        parent_dir = rel.parts[0]
        return DIR_TO_TYPE.get(parent_dir)
    return None


def _infer_type_from_name(filename: str) -> str | None:
    """Infer doc type from filename convention {module}_{type}_en.md."""
    m = re.match(r".*_(api|arch|tech|user|sec|spec)_en\.md$", filename)
    if m:
        type_map = {
            "api": "API", "arch": "ARCH", "tech": "TECH",
            "user": "USER", "sec": "SEC", "spec": "SPEC",
        }
        return type_map.get(m.group(1))
    return None


def _infer_type_from_content_hints(filename: str) -> str | None:
    """Infer doc type from filename keywords."""
    lower = filename.lower()
    # Plans and designs -> SPEC
    if any(kw in lower for kw in ("plan", "design", "spec", "requirement")):
        return "SPEC"
    # Guides -> USER
    if any(kw in lower for kw in ("guide", "howto", "tutorial", "quickstart")):
        return "USER"
    # Architecture -> ARCH
    if any(kw in lower for kw in ("arch", "architecture", "overview", "diagram")):
        return "ARCH"
    # API -> API
    if any(kw in lower for kw in ("api", "endpoint", "reference")):
        return "API"
    # Security -> SEC
    if any(kw in lower for kw in ("security", "hardening", "audit", "threat")):
        return "SEC"
    return None


def _suggest_name(doc_path: Path, doc_type: str) -> str:
    """Suggest a compliant filename based on the document content and type."""
    stem = doc_path.stem
    type_suffix = doc_type.lower()

    # Already compliant
    if NAMING_PATTERN.match(doc_path.name):
        return doc_path.name

    # Remove existing _en suffix
    stem = re.sub(r"_en$", "", stem)

    # Remove existing type suffix if present
    for t in ("api", "arch", "tech", "user", "sec", "spec"):
        stem = re.sub(rf"_{t}$", "", stem)

    # Normalize: lowercase, underscores, no special chars
    stem = stem.lower()
    stem = re.sub(r"[^a-z0-9_]", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")

    # Strip leading date prefix for cleaner names (2026_03_06_ -> keep module part)
    stem = re.sub(r"^\d{4}_\d{2}_\d{2}_", "", stem)

    if not stem:
        stem = "unnamed"

    return f"{stem}_{type_suffix}_en.md"


def _days_since(date_str: str) -> int:
    """Days since a date string (YYYY-MM-DD)."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 9999


# ---------------------------------------------------------------------------
# Issue collector
# ---------------------------------------------------------------------------

class Issue:
    """Single audit issue."""
    def __init__(self, severity: str, category: str, path: str, message: str, fix: str = ""):
        self.severity = severity   # CRITICAL, HIGH, MEDIUM, LOW, INFO
        self.category = category   # NAMING, ORGANIZATION, VERSIONING, STALENESS, METADATA, INDEX
        self.path = path
        self.message = message
        self.fix = fix

    def __repr__(self):
        return f"[{self.severity}] {self.category}: {self.path} -- {self.message}"


# ---------------------------------------------------------------------------
# Audit engine
# ---------------------------------------------------------------------------

def audit_naming(base: Path, docs: list[Path]) -> list[Issue]:
    """Check naming convention compliance."""
    issues = []
    for doc in docs:
        if not NAMING_PATTERN.match(doc.name):
            meta = _load_meta(doc)
            doc_type = (meta or {}).get("type", "TECH")
            suggested = _suggest_name(doc, doc_type)
            issues.append(Issue(
                "MEDIUM", "NAMING", str(doc.relative_to(base)),
                f"Non-compliant filename (expected: {{module}}_{{type}}_en.md)",
                f"Rename to: {suggested}"
            ))
    return issues


def audit_organization(base: Path, docs: list[Path]) -> list[Issue]:
    """Check files are in the correct type directory."""
    issues = []
    for doc in docs:
        meta = _load_meta(doc)
        if not meta:
            continue
        doc_type = meta.get("type", "TECH")
        expected_dir = TYPE_TO_DIR.get(doc_type, "technical")
        rel = doc.relative_to(base)
        actual_dir = rel.parts[0] if len(rel.parts) >= 2 else None

        if actual_dir and actual_dir not in (expected_dir, DIAGRAMS_DIR, EXPORTS_DIR):
            issues.append(Issue(
                "MEDIUM", "ORGANIZATION", str(rel),
                f"File in '{actual_dir}/' but type is {doc_type} (expected: '{expected_dir}/')",
                f"Move to {expected_dir}/{doc.name}"
            ))
        elif actual_dir is None:
            # File at root of docs/
            issues.append(Issue(
                "LOW", "ORGANIZATION", str(rel),
                f"File at docs/ root, should be in '{expected_dir}/'",
                f"Move to {expected_dir}/{doc.name}"
            ))
    return issues


def audit_metadata(base: Path, docs: list[Path]) -> list[Issue]:
    """Check metadata presence and completeness."""
    issues = []
    for doc in docs:
        meta = _load_meta(doc)
        rel = str(doc.relative_to(base))

        if meta is None:
            issues.append(Issue(
                "HIGH", "METADATA", rel,
                "Missing .doc-meta.json sidecar",
                f"Run: python3 doc_classifier.py init {doc}"
            ))
            continue

        # Required fields
        for field in ("title", "type", "version", "status", "author", "created", "updated"):
            if not meta.get(field):
                issues.append(Issue(
                    "HIGH", "METADATA", rel,
                    f"Missing required field: {field}",
                    f"Update .doc-meta.json"
                ))

        # Version history
        if not meta.get("version_history"):
            issues.append(Issue(
                "MEDIUM", "VERSIONING", rel,
                "Empty version_history",
                "Add version history entries"
            ))

        # Type consistency
        inferred = _infer_type_from_name(doc.name)
        if inferred and meta.get("type") != inferred:
            issues.append(Issue(
                "LOW", "METADATA", rel,
                f"Filename suggests type {inferred} but metadata says {meta.get('type')}",
                f"Align filename or metadata type"
            ))

    return issues


def audit_freshness(base: Path, docs: list[Path], max_age: int = 90) -> list[Issue]:
    """Detect stale docs by comparing metadata update date vs threshold."""
    issues = []
    for doc in docs:
        meta = _load_meta(doc)
        if not meta:
            continue

        rel = str(doc.relative_to(base))
        updated = meta.get("updated", "")
        status = meta.get("status", "DRAFT")

        # Skip archived docs
        if status == "ARCHIVED":
            continue

        age = _days_since(updated)

        if age > max_age * 2:
            issues.append(Issue(
                "HIGH", "STALENESS", rel,
                f"Document is {age} days old (last updated: {updated}). "
                f"Likely obsolete -- consider archiving or updating.",
                f"Archive: mv {doc} {base / ARCHIVE_DIR / doc.name}"
            ))
        elif age > max_age:
            issues.append(Issue(
                "MEDIUM", "STALENESS", rel,
                f"Document is {age} days old (last updated: {updated}). "
                f"May need refresh.",
                f"Review and bump: python3 doc_classifier.py bump {doc} patch"
            ))

    return issues


def audit_index(base: Path) -> list[Issue]:
    """Check INDEX.md existence and freshness."""
    issues = []
    index_path = base / "INDEX.md"

    if not index_path.exists():
        issues.append(Issue(
            "HIGH", "INDEX", "INDEX.md",
            "INDEX.md does not exist",
            f"Run: python3 doc_classifier.py index {base} -o {index_path}"
        ))
        return issues

    # Check if index is older than any doc metadata
    index_mtime = datetime.fromtimestamp(index_path.stat().st_mtime).date()
    for mp in _find_metas(base):
        meta_mtime = datetime.fromtimestamp(mp.stat().st_mtime).date()
        if meta_mtime > index_mtime:
            issues.append(Issue(
                "MEDIUM", "INDEX", "INDEX.md",
                f"INDEX.md is outdated (metadata {mp.name} was modified after index)",
                f"Run: python3 doc_classifier.py index {base} -o {index_path}"
            ))
            break

    return issues


def audit_orphan_meta(base: Path) -> list[Issue]:
    """Find .doc-meta.json files without a corresponding .md file."""
    issues = []
    for mp in _find_metas(base):
        # Derive expected doc filename
        doc_name = mp.name.lstrip(".").replace(".doc-meta.json", ".md")
        doc_path = mp.parent / doc_name
        if not doc_path.exists():
            rel = str(mp.relative_to(base))
            issues.append(Issue(
                "LOW", "METADATA", rel,
                f"Orphan metadata: no corresponding {doc_name}",
                f"Delete metadata or restore document"
            ))
    return issues


def audit_duplicates(base: Path, docs: list[Path]) -> list[Issue]:
    """Detect docs covering the same module (by title similarity)."""
    issues = []
    titles: dict[str, list[Path]] = {}
    for doc in docs:
        meta = _load_meta(doc)
        if meta and meta.get("title"):
            key = meta["title"].lower().strip()
            titles.setdefault(key, []).append(doc)

    for title, paths in titles.items():
        if len(paths) > 1:
            rel_paths = [str(p.relative_to(base)) for p in paths]
            issues.append(Issue(
                "HIGH", "ORGANIZATION", ", ".join(rel_paths),
                f"Duplicate docs with title '{title}' ({len(paths)} copies)",
                "Consolidate into one, archive the rest"
            ))
    return issues


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_audit(args: argparse.Namespace) -> None:
    """Full health audit of documentation directory."""
    base = Path(args.directory)
    if not base.is_dir():
        print(f"Error: {base} is not a directory", file=sys.stderr)
        sys.exit(2)

    docs = _find_docs(base)
    print(f"\n=== LIA-SEC Documentation Librarian Audit ===")
    print(f"Directory: {base}")
    print(f"Documents found: {len(docs)}")
    print(f"Metadata files: {len(_find_metas(base))}")
    print()

    all_issues: list[Issue] = []
    all_issues.extend(audit_naming(base, docs))
    all_issues.extend(audit_organization(base, docs))
    all_issues.extend(audit_metadata(base, docs))
    all_issues.extend(audit_freshness(base, docs, max_age=args.max_age))
    all_issues.extend(audit_index(base))
    all_issues.extend(audit_orphan_meta(base))
    all_issues.extend(audit_duplicates(base, docs))

    if not all_issues:
        print("HEALTHY: No issues found.")
        sys.exit(0)

    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    all_issues.sort(key=lambda i: severity_order.get(i.severity, 5))

    # Summary
    by_severity = {}
    by_category = {}
    for issue in all_issues:
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        by_category[issue.category] = by_category.get(issue.category, 0) + 1

    print("--- Summary ---")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
        count = by_severity.get(sev, 0)
        if count:
            print(f"  {sev}: {count}")
    print()

    print("--- By Category ---")
    for cat, count in sorted(by_category.items()):
        print(f"  {cat}: {count}")
    print()

    print("--- Details ---")
    for issue in all_issues:
        print(f"  [{issue.severity}] {issue.category}: {issue.path}")
        print(f"    {issue.message}")
        if issue.fix:
            print(f"    FIX: {issue.fix}")
        print()

    total = len(all_issues)
    critical = by_severity.get("CRITICAL", 0) + by_severity.get("HIGH", 0)
    print(f"Total: {total} issues ({critical} critical/high)")

    sys.exit(2 if by_severity.get("CRITICAL", 0) > 0 else 1)


def cmd_organize(args: argparse.Namespace) -> None:
    """Move misplaced files to correct type directories."""
    base = Path(args.directory)
    docs = _find_docs(base)
    dry_run = args.dry_run
    moved = 0

    for doc in docs:
        meta = _load_meta(doc)
        if not meta:
            continue

        doc_type = meta.get("type", "TECH")
        expected_dir = TYPE_TO_DIR.get(doc_type, "technical")
        rel = doc.relative_to(base)
        actual_dir = rel.parts[0] if len(rel.parts) >= 2 else None

        if actual_dir == expected_dir:
            continue
        if actual_dir in (DIAGRAMS_DIR, EXPORTS_DIR, ARCHIVE_DIR):
            continue

        target_dir = base / expected_dir
        target_path = target_dir / doc.name
        meta_src = _meta_path(doc)
        meta_dst = _meta_path(target_path)

        if dry_run:
            print(f"[DRY-RUN] Would move: {rel} -> {expected_dir}/{doc.name}")
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(doc), str(target_path))
            if meta_src.exists():
                shutil.move(str(meta_src), str(meta_dst))
            print(f"Moved: {rel} -> {expected_dir}/{doc.name}")
        moved += 1

    print(f"\n{'Would move' if dry_run else 'Moved'}: {moved} file(s)")


def cmd_rename(args: argparse.Namespace) -> None:
    """Rename files to match naming convention."""
    base = Path(args.directory)
    docs = _find_docs(base)
    dry_run = args.dry_run
    renamed = 0

    for doc in docs:
        if NAMING_PATTERN.match(doc.name):
            continue

        meta = _load_meta(doc)
        doc_type = ((meta or {}).get("type")
                    or _infer_type_from_dir(doc, base)
                    or _infer_type_from_content_hints(doc.name)
                    or "TECH")
        suggested = _suggest_name(doc, doc_type)

        if suggested == doc.name:
            continue

        target = doc.parent / suggested
        if target.exists():
            print(f"SKIP: {doc.name} -> {suggested} (target already exists)")
            continue

        meta_src = _meta_path(doc)
        meta_dst = _meta_path(target)

        if dry_run:
            print(f"[DRY-RUN] Would rename: {doc.name} -> {suggested}")
        else:
            doc.rename(target)
            if meta_src.exists():
                meta_src.rename(meta_dst)
            print(f"Renamed: {doc.name} -> {suggested}")
        renamed += 1

    print(f"\n{'Would rename' if dry_run else 'Renamed'}: {renamed} file(s)")


def cmd_freshness(args: argparse.Namespace) -> None:
    """Check document freshness against age threshold."""
    base = Path(args.directory)
    docs = _find_docs(base)
    max_age = args.max_age

    print(f"\n=== Freshness Report (threshold: {max_age} days) ===\n")
    print(f"{'Document':<45} {'Updated':<12} {'Age':<8} {'Status':<10} {'Verdict'}")
    print("-" * 100)

    stale_count = 0
    for doc in docs:
        meta = _load_meta(doc)
        if not meta:
            rel = str(doc.relative_to(base))
            print(f"{rel:<45} {'N/A':<12} {'N/A':<8} {'NO META':<10} UNKNOWN")
            continue

        updated = meta.get("updated", "")
        status = meta.get("status", "DRAFT")
        age = _days_since(updated)
        rel = str(doc.relative_to(base))

        if status == "ARCHIVED":
            verdict = "ARCHIVED"
        elif age > max_age * 2:
            verdict = "OBSOLETE"
            stale_count += 1
        elif age > max_age:
            verdict = "STALE"
            stale_count += 1
        else:
            verdict = "CURRENT"

        print(f"{rel:<45} {updated:<12} {age:<8} {status:<10} {verdict}")

    print(f"\nTotal: {len(docs)} docs, {stale_count} stale/obsolete")
    sys.exit(1 if stale_count > 0 else 0)


def cmd_reindex(args: argparse.Namespace) -> None:
    """Regenerate INDEX.md with full catalog including freshness indicators."""
    base = Path(args.directory)
    output_path = Path(args.output) if args.output else base / "INDEX.md"

    meta_files = sorted(base.rglob(".*.doc-meta.json"))
    if not meta_files:
        print(f"No documentation metadata found in {base}")
        return

    # Load all metadata
    entries: list[dict] = []
    for mp in meta_files:
        # Skip archive
        rel = mp.relative_to(base)
        if ARCHIVE_DIR in rel.parts:
            continue
        with open(mp, encoding="utf-8") as f:
            m = json.load(f)
        doc_name = mp.name.lstrip(".").replace(".doc-meta.json", "")
        m["_filename"] = doc_name
        m["_dir"] = str(rel.parent)
        m["_age"] = _days_since(m.get("updated", ""))
        entries.append(m)

    # Group by type
    by_type: dict[str, list[dict]] = {}
    for entry in entries:
        dtype = entry.get("type", "TECH")
        by_type.setdefault(dtype, []).append(entry)

    today = date.today().isoformat()

    lines = [
        "# LIA-SEC Documentation Index",
        "",
        f"> Generated: {today} | Librarian v1.0 | Platform: LIA-Security v2",
        "",
        "## Summary",
        "",
        "| Type | Count | Current | Stale | Obsolete |",
        "|------|-------|---------|-------|----------|",
    ]

    for dtype in sorted(by_type.keys()):
        docs = by_type[dtype]
        current = sum(1 for d in docs if d["_age"] <= 90 and d.get("status") != "ARCHIVED")
        stale = sum(1 for d in docs if 90 < d["_age"] <= 180 and d.get("status") != "ARCHIVED")
        obsolete = sum(1 for d in docs if d["_age"] > 180 and d.get("status") != "ARCHIVED")
        label = DOC_TYPES.get(dtype, dtype)
        lines.append(f"| {label} | {len(docs)} | {current} | {stale} | {obsolete} |")

    total = len(entries)
    total_current = sum(1 for e in entries if e["_age"] <= 90 and e.get("status") != "ARCHIVED")
    lines.append(f"| **Total** | **{total}** | **{total_current}** | | |")

    lines.extend(["", "---", ""])

    for dtype in sorted(by_type.keys()):
        docs = by_type[dtype]
        label = DOC_TYPES.get(dtype, dtype)
        target_dir = TYPE_TO_DIR.get(dtype, "technical")
        lines.append(f"## {label} (`{target_dir}/`)")
        lines.append("")
        lines.append("| Document | Version | Status | Updated | Age | Health |")
        lines.append("|----------|---------|--------|---------|-----|--------|")

        for doc in sorted(docs, key=lambda d: d.get("title", "")):
            title = doc.get("title", doc["_filename"])
            version = doc.get("version", "-")
            status = doc.get("status", "-")
            updated = doc.get("updated", "-")
            age = doc["_age"]

            if status == "ARCHIVED":
                health = "ARCHIVED"
            elif age <= 90:
                health = "CURRENT"
            elif age <= 180:
                health = "STALE"
            else:
                health = "OBSOLETE"

            path = f"{doc['_dir']}/{doc['_filename']}.md" if doc["_dir"] != "." else f"{doc['_filename']}.md"
            lines.append(
                f"| [{title}]({path}) | {version} | {status} | {updated} | {age}d | {health} |"
            )

        lines.append("")

    # Archive section
    archive_path = base / ARCHIVE_DIR
    if archive_path.is_dir():
        archived = sorted(archive_path.glob("*.md"))
        if archived:
            lines.append(f"## Archive (`{ARCHIVE_DIR}/`)")
            lines.append("")
            lines.append(f"{len(archived)} archived document(s)")
            lines.append("")
            for a in archived:
                lines.append(f"- {a.name}")
            lines.append("")

    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")
    print(f"Index written to {output_path}")
    print(f"Total: {total} documented file(s), {total_current} current")


def cmd_fix(args: argparse.Namespace) -> None:
    """Auto-fix all issues: missing metadata, wrong directory, bad names, stale index."""
    base = Path(args.directory)
    docs = _find_docs(base)
    dry_run = args.dry_run
    auto = args.auto
    fixed = 0

    print(f"\n=== LIA-SEC Librarian Fix ===")
    print(f"Directory: {base}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'AUTO' if auto else 'INTERACTIVE'}")
    print()

    # 1. Create missing directories
    for dir_name in TYPE_TO_DIR.values():
        target = base / dir_name
        if not target.exists():
            if dry_run:
                print(f"[DRY-RUN] Would create: {target}/")
            else:
                target.mkdir(parents=True, exist_ok=True)
                print(f"Created: {target}/")
            fixed += 1

    archive = base / ARCHIVE_DIR
    if not archive.exists():
        if dry_run:
            print(f"[DRY-RUN] Would create: {archive}/")
        else:
            archive.mkdir(parents=True, exist_ok=True)
            print(f"Created: {archive}/")

    exports = base / EXPORTS_DIR
    if not exports.exists():
        if dry_run:
            print(f"[DRY-RUN] Would create: {exports}/")
        else:
            exports.mkdir(parents=True, exist_ok=True)
            print(f"Created: {exports}/")

    # 2. Initialize missing metadata
    for doc in docs:
        if _load_meta(doc) is None:
            inferred_type = (_infer_type_from_name(doc.name)
                            or _infer_type_from_dir(doc, base)
                            or _infer_type_from_content_hints(doc.name)
                            or "TECH")
            title = doc.stem.replace("_", " ").replace("-", " ").title()
            # Remove type and lang suffix from title
            for suffix in (" Api En", " Arch En", " Tech En", " User En", " Sec En", " Spec En"):
                title = title.replace(suffix, "")

            if dry_run:
                print(f"[DRY-RUN] Would init metadata: {doc.name} (type={inferred_type})")
            else:
                today = date.today().isoformat()
                meta = {
                    "title": title.strip(),
                    "subtitle": "",
                    "type": inferred_type,
                    "classification": "INTERNAL",
                    "version": "1.0.0",
                    "status": "DRAFT",
                    "author": "mo0ogly@proton.me",
                    "created": today,
                    "updated": today,
                    "platform": "LIA-Security v2",
                    "description": "",
                    "tags": [],
                    "version_history": [{
                        "version": "1.0.0",
                        "date": today,
                        "author": "mo0ogly@proton.me",
                        "description": "Initial version (auto-generated by librarian)"
                    }]
                }
                _save_meta(doc, meta)
                print(f"Initialized metadata: {doc.name} (type={inferred_type})")
            fixed += 1

    # 3. Rename non-compliant files
    for doc in _find_docs(base):  # Re-scan after metadata init
        if NAMING_PATTERN.match(doc.name):
            continue

        meta = _load_meta(doc)
        doc_type = ((meta or {}).get("type")
                    or _infer_type_from_dir(doc, base)
                    or _infer_type_from_content_hints(doc.name)
                    or "TECH")
        suggested = _suggest_name(doc, doc_type)

        if suggested == doc.name:
            continue

        target = doc.parent / suggested
        if target.exists():
            continue

        proceed = auto
        if not auto and not dry_run:
            resp = input(f"  Rename '{doc.name}' -> '{suggested}'? [y/N] ").strip().lower()
            proceed = resp == "y"

        if proceed or dry_run:
            if dry_run:
                print(f"[DRY-RUN] Would rename: {doc.name} -> {suggested}")
            else:
                meta_src = _meta_path(doc)
                meta_dst = _meta_path(target)
                doc.rename(target)
                if meta_src.exists():
                    meta_src.rename(meta_dst)
                print(f"Renamed: {doc.name} -> {suggested}")
            fixed += 1

    # 4. Organize files into correct directories
    for doc in _find_docs(base):  # Re-scan after rename
        meta = _load_meta(doc)
        if not meta:
            continue

        doc_type = meta.get("type", "TECH")
        expected_dir = TYPE_TO_DIR.get(doc_type, "technical")
        rel = doc.relative_to(base)
        actual_dir = rel.parts[0] if len(rel.parts) >= 2 else None

        if actual_dir == expected_dir:
            continue
        if actual_dir in (DIAGRAMS_DIR, EXPORTS_DIR, ARCHIVE_DIR):
            continue

        target_dir = base / expected_dir
        target_path = target_dir / doc.name

        if target_path.exists():
            continue

        proceed = auto
        if not auto and not dry_run:
            resp = input(f"  Move '{rel}' -> '{expected_dir}/{doc.name}'? [y/N] ").strip().lower()
            proceed = resp == "y"

        if proceed or dry_run:
            if dry_run:
                print(f"[DRY-RUN] Would move: {rel} -> {expected_dir}/{doc.name}")
            else:
                target_dir.mkdir(parents=True, exist_ok=True)
                meta_src = _meta_path(doc)
                meta_dst = _meta_path(target_path)
                shutil.move(str(doc), str(target_path))
                if meta_src.exists():
                    shutil.move(str(meta_src), str(meta_dst))
                print(f"Moved: {rel} -> {expected_dir}/{doc.name}")
            fixed += 1

    # 5. Regenerate index
    index_path = base / "INDEX.md"
    if dry_run:
        print(f"[DRY-RUN] Would regenerate: {index_path}")
    else:
        # Simulate reindex inline
        args_ns = argparse.Namespace(directory=str(base), output=str(index_path))
        cmd_reindex(args_ns)
    fixed += 1

    print(f"\n{'Would fix' if dry_run else 'Fixed'}: {fixed} item(s)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LIA-SEC Documentation Librarian v1.0 | mo0ogly@proton.me",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # audit
    p_audit = sub.add_parser("audit", help="Full documentation health audit")
    p_audit.add_argument("directory", help="Documentation root directory")
    p_audit.add_argument("--max-age", type=int, default=90, help="Staleness threshold in days (default: 90)")

    # organize
    p_org = sub.add_parser("organize", help="Move files to correct type directories")
    p_org.add_argument("directory", help="Documentation root directory")
    p_org.add_argument("--dry-run", action="store_true", help="Show what would be done")

    # rename
    p_rename = sub.add_parser("rename", help="Rename files to match naming convention")
    p_rename.add_argument("directory", help="Documentation root directory")
    p_rename.add_argument("--dry-run", action="store_true", help="Show what would be done")

    # freshness
    p_fresh = sub.add_parser("freshness", help="Check document freshness")
    p_fresh.add_argument("directory", help="Documentation root directory")
    p_fresh.add_argument("--max-age", type=int, default=90, help="Staleness threshold in days (default: 90)")

    # reindex
    p_reindex = sub.add_parser("reindex", help="Regenerate INDEX.md with health indicators")
    p_reindex.add_argument("directory", help="Documentation root directory")
    p_reindex.add_argument("-o", "--output", help="Output INDEX.md path")

    # fix
    p_fix = sub.add_parser("fix", help="Auto-fix all issues (metadata, naming, organization, index)")
    p_fix.add_argument("directory", help="Documentation root directory")
    p_fix.add_argument("--dry-run", action="store_true", help="Show what would be done")
    p_fix.add_argument("--auto", action="store_true", help="Auto-approve all renames and moves")

    args = parser.parse_args()

    commands = {
        "audit":     cmd_audit,
        "organize":  cmd_organize,
        "rename":    cmd_rename,
        "freshness": cmd_freshness,
        "reindex":   cmd_reindex,
        "fix":       cmd_fix,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
