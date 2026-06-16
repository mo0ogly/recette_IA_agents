#!/usr/bin/env python3
"""
doc_classifier.py - Documentation metadata manager for LIA-SEC

Commands:
  init <file> [--type TYPE]   Initialize .doc-meta.json sidecar
  bump <file> [--minor|--major] [--desc "description"]  Bump version
  status <file>               Show metadata status
  show <file>                 Show full metadata
  list <dir>                  List all docs with metadata
  index <dir>                 Generate INDEX.md from metadata

Types: TECH, API, ARCH, USER, SEC, SPEC
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

AUTHOR = "mo0ogly@proton.me"
PLATFORM = "LIA-Security v2"

VALID_TYPES = {"TECH", "API", "ARCH", "USER", "SEC", "SPEC"}
VALID_STATUSES = {"DRAFT", "REVIEW", "CURRENT", "STALE", "OBSOLETE", "ARCHIVED"}
VALID_CLASSIFICATIONS = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"}

TYPE_LABELS = {
    "TECH": "Technical Documentation",
    "API": "API Reference",
    "ARCH": "Architecture Document",
    "USER": "User Guide",
    "SEC": "Security Documentation",
    "SPEC": "Functional Specification",
}


def meta_path(filepath: str) -> str:
    """Get the .doc-meta.json sidecar path for a given .md file."""
    p = Path(filepath)
    return str(p.parent / f".{p.stem}.doc-meta.json")


def title_from_filename(filepath: str) -> str:
    """Generate a title from the filename."""
    stem = Path(filepath).stem
    # Remove _en suffix and underscores
    title = stem.replace("_en", "").replace("_", " ").title()
    return title


def init_metadata(filepath: str, doc_type: str = "TECH") -> dict:
    """Create initial metadata for a document."""
    doc_type = doc_type.upper()
    if doc_type not in VALID_TYPES:
        print(f"Invalid type: {doc_type}. Valid: {', '.join(VALID_TYPES)}")
        sys.exit(1)

    today = date.today().isoformat()
    meta = {
        "title": title_from_filename(filepath),
        "subtitle": "",
        "type": doc_type,
        "classification": "INTERNAL",
        "version": "1.0.0",
        "status": "DRAFT",
        "author": AUTHOR,
        "created": today,
        "updated": today,
        "platform": PLATFORM,
        "description": "",
        "tags": [],
        "version_history": [
            {
                "version": "1.0.0",
                "date": today,
                "author": AUTHOR,
                "description": "Initial version",
            }
        ],
    }
    return meta


def bump_version(meta: dict, level: str = "patch", description: str = "") -> dict:
    """Bump the version of a document."""
    parts = meta.get("version", "1.0.0").split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if level == "major":
        major += 1
        minor = 0
        patch = 0
    elif level == "minor":
        major = major
        minor += 1
        patch = 0
    else:
        patch += 1

    new_version = f"{major}.{minor}.{patch}"
    today = date.today().isoformat()

    meta["version"] = new_version
    meta["updated"] = today
    meta["status"] = "DRAFT"

    history = meta.get("version_history", [])
    history.append(
        {
            "version": new_version,
            "date": today,
            "author": AUTHOR,
            "description": description or f"Version bump ({level})",
        }
    )
    meta["version_history"] = history
    return meta


def save_meta(filepath: str, meta: dict):
    """Save metadata to .doc-meta.json sidecar."""
    mp = meta_path(filepath)
    with open(mp, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"Metadata saved to {mp}")


def load_meta(filepath: str) -> dict:
    """Load metadata from .doc-meta.json sidecar."""
    mp = meta_path(filepath)
    if not os.path.exists(mp):
        return None
    with open(mp) as f:
        return json.load(f)


def cmd_init(args):
    filepath = args[0]
    doc_type = "TECH"
    if "--type" in args:
        idx = args.index("--type")
        if idx + 1 < len(args):
            doc_type = args[idx + 1]

    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    meta = init_metadata(filepath, doc_type)
    save_meta(filepath, meta)

    print(f"\nInitialized documentation metadata:")
    print(f"  Title          : {meta['title']}")
    print(f"  Type           : {meta['type']} ({TYPE_LABELS.get(meta['type'], '')})")
    print(f"  Version        : {meta['version']}")
    print(f"  Classification : {meta['classification']}")


def cmd_bump(args):
    filepath = args[0]
    level = "patch"
    description = ""

    if "--minor" in args:
        level = "minor"
    elif "--major" in args:
        level = "major"

    if "--desc" in args:
        idx = args.index("--desc")
        if idx + 1 < len(args):
            description = args[idx + 1]

    meta = load_meta(filepath)
    if meta is None:
        print(f"No metadata found for {filepath}. Run 'init' first.")
        sys.exit(1)

    old_version = meta["version"]
    meta = bump_version(meta, level, description)
    save_meta(filepath, meta)
    print(f"\nBumped: {old_version} -> {meta['version']} ({level})")


def cmd_status(args):
    filepath = args[0]
    meta = load_meta(filepath)
    if meta is None:
        print(f"No metadata: {filepath}")
        return
    print(f"{meta['version']} | {meta['status']} | {meta['type']} | {meta['title']}")


def cmd_show(args):
    filepath = args[0]
    meta = load_meta(filepath)
    if meta is None:
        print(f"No metadata: {filepath}")
        return
    print(json.dumps(meta, indent=2))


def cmd_list(args):
    directory = args[0] if args else "_alire/01_DOCUMENTATION/"
    count = 0
    for root, dirs, files in os.walk(directory):
        for f in sorted(files):
            if f.endswith(".md") and not f.startswith(".") and f != "INDEX.md":
                fp = os.path.join(root, f)
                meta = load_meta(fp)
                if meta:
                    status_icon = {"CURRENT": "OK", "DRAFT": "DR", "STALE": "ST", "OBSOLETE": "OB"}.get(meta.get("status", ""), "??")
                    print(f"[{status_icon}] {meta['version']:>7} | {meta['type']:>4} | {meta['title']}")
                    count += 1
                else:
                    print(f"[--] no-meta | ---- | {f}")
                    count += 1
    print(f"\nTotal: {count} document(s)")


def cmd_index(args):
    directory = args[0] if args else "_alire/01_DOCUMENTATION/"
    docs = []
    for root, dirs, files in os.walk(directory):
        for f in sorted(files):
            if f.endswith(".md") and not f.startswith(".") and f != "INDEX.md":
                fp = os.path.join(root, f)
                meta = load_meta(fp)
                rel = os.path.relpath(fp, directory)
                if meta:
                    docs.append((rel, meta))
                else:
                    docs.append((rel, {"title": f, "type": "?", "version": "?", "status": "?"}))

    lines = ["# Documentation Index\n"]
    lines.append(f"> Auto-generated on {date.today().isoformat()} | {len(docs)} documents\n")
    lines.append("| File | Type | Version | Status | Title |")
    lines.append("|------|------|---------|--------|-------|")
    for rel, meta in sorted(docs):
        lines.append(f"| [{rel}]({rel}) | {meta.get('type', '?')} | {meta.get('version', '?')} | {meta.get('status', '?')} | {meta.get('title', '?')} |")

    output = os.path.join(directory, "INDEX.md")
    with open(output, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Index written to {output}")
    print(f"Total: {len(docs)} documented file(s), {sum(1 for _, m in docs if m.get('status') == 'CURRENT')} current")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "init": cmd_init,
        "bump": cmd_bump,
        "status": cmd_status,
        "show": cmd_show,
        "list": cmd_list,
        "index": cmd_index,
    }

    if cmd in commands:
        if cmd in ("init", "bump", "status", "show") and not args:
            print(f"Usage: doc_classifier.py {cmd} <file>")
            sys.exit(1)
        commands[cmd](args)
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands.keys())}")
        sys.exit(1)


if __name__ == "__main__":
    main()
