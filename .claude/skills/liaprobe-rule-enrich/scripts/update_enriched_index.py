#!/usr/bin/env python3
"""
update_enriched_index -- Refresh ENRICHED_RULES.md from per-rule state files.

Scans `<liaprobe-root>/_alire/tracking/liaprobe-enrich-v2/runtime/enrich_state/*.state.json`,
reads each enriched rule, and rebuilds the registry table in ENRICHED_RULES.md.

The runtime state lives under --liaprobe-root (gitignored in the public
liaprobe repo), but the ENRICHED_RULES.md dashboard is written to the
committed LIA-SEC dev tracking dir so it stays version-controlled (R7).

Usage:
    python3 update_enriched_index.py [--liaprobe-root PATH] [--index-out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone


REGISTRY_HEADER = "## Enriched rules registry"
LIFECYCLE_HEADER = "## Lifecycle state per rule (lia-enrich-state-v1)"
LAST_UPDATE_PREFIX = "**Last update**"
TOTAL_ENRICHED_PREFIX = "**Enriched**"


def _resolve_liaprobe_root() -> Path:
    env = os.environ.get("LIAPROBE_ROOT")
    if env:
        p = Path(env).resolve()
        if p.exists():
            return p
    return Path("/opt/lia-sec/liaprobe").resolve()


TRACKING_REL = "_alire/tracking/liaprobe-enrich-v2"


def _resolve_index_path() -> Path:
    """Resolve the canonical (committed) ENRICHED_RULES.md in the LIA-SEC dev
    repo. The enrich runtime state lives under --liaprobe-root, but that path
    is gitignored in the public liaprobe repo, so the index dashboard must be
    written to the dev tracking dir to be version-controlled (R7 re-scatter
    fix). Walk up from this script until a dir containing the tracking subtree
    is found; fall back to the known dev mirror path."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / TRACKING_REL
        if candidate.is_dir():
            return candidate / "ENRICHED_RULES.md"
    return Path("/opt/lia-sec/dev") / TRACKING_REL / "ENRICHED_RULES.md"


def _read_rule(rule_path: Path) -> dict:
    try:
        with rule_path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _summary_table(states: list[dict], roots: dict) -> str:
    lines = [
        "| Rule | Path | Cycles | CVE | KEV | Critical | EOL? | ATT&CK | Score | Verdict | Last enriched |",
        "|------|------|--------|-----|-----|----------|------|--------|-------|---------|---------------|",
    ]
    for st in sorted(states, key=lambda s: s.get("rule", {}).get("path", "")):
        rule_path = Path(st.get("rule", {}).get("path", ""))
        rule_data = _read_rule(rule_path)
        rid = rule_data.get("id", rule_path.stem)
        rel_path = str(rule_path.relative_to(roots["liaprobe"])) if rule_path.is_absolute() else str(rule_path)
        cycles = st.get("cycles", {})
        c4 = cycles.get("cycle_4_cve", {})
        c5 = cycles.get("cycle_5_eol", {})
        c7 = cycles.get("cycle_7_mitre", {})
        completed_cycles = [
            cid.replace("cycle_", "").replace("_cve", "").replace("_eol", "").replace("_mitre", "")
            for cid, c in cycles.items()
            if c.get("status") == "completed"
        ]
        cycles_str = "+".join(sorted(completed_cycles)) if completed_cycles else "-"
        cve_count = c4.get("summary", {}).get("cve_count", "-")
        kev_count = c4.get("summary", {}).get("kev_count", "-")
        critical_count = c4.get("summary", {}).get("critical_count", "-")
        eol_now = c5.get("summary", {}).get("is_eol_now")
        latest_cycle = c5.get("summary", {}).get("latest_cycle")
        eol_str = "EOL" if eol_now else (f"NO ({latest_cycle})" if latest_cycle else "-")
        techniques = c7.get("summary", {}).get("techniques_count", "-")
        score = rule_data and _compute_score(rule_data) or "-"
        last_at = st.get("last_enriched_at", "-")
        lines.append(
            f"| {rid} | {rel_path} | {cycles_str} | {cve_count} | {kev_count} | {critical_count} | {eol_str} | {techniques} | {score} | {st.get('lifecycle_state', '-')} | {last_at} |"
        )
    return "\n".join(lines)


def _lifecycle_table(states: list[dict]) -> str:
    lines = [
        "| Rule | Lifecycle state | First enriched | Last enriched | Cycles done | Cycles skipped |",
        "|------|----------------|----------------|---------------|-------------|----------------|",
    ]
    for st in sorted(states, key=lambda s: s.get("rule", {}).get("path", "")):
        rule_path = Path(st.get("rule", {}).get("path", ""))
        rid = rule_path.stem
        cycles = st.get("cycles", {})
        done = [c for c, x in cycles.items() if x.get("status") == "completed"]
        skipped = [c for c, x in cycles.items() if x.get("status") == "skipped"]
        lines.append(
            f"| {rid} | {st.get('lifecycle_state', '-')} | {st.get('first_enriched_at', '-')} | {st.get('last_enriched_at', '-')} | {', '.join(sorted(done)) or '-'} | {', '.join(sorted(skipped)) or '-'} |"
        )
    return "\n".join(lines)


def _compute_score(rule_data: dict) -> float:
    weights = {
        "known_cves": 25, "lifecycle": 15, "attack_surface": 20,
        "compliance": 15, "default_credentials": 10, "common_misconfigs": 5,
        "behavior": 5, "plugins": 3, "cluster_topology": 1, "tls_signals": 1,
    }
    total = 0.0
    for k, w in weights.items():
        v = rule_data.get(k)
        if (isinstance(v, list) and v) or (isinstance(v, dict) and v):
            total += w
    return round(total, 1)


def _replace_section(content: str, header: str, new_table: str) -> str:
    """Replace lines from `header` until next `## ` header."""
    lines = content.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == header:
            out.append(line)
            out.append("")
            out.append(new_table)
            i += 1
            # skip until next section header (starting with "## ")
            while i < len(lines) and not (lines[i].startswith("## ") and lines[i] != header):
                i += 1
            if i < len(lines):
                out.append("")
        else:
            out.append(line)
            i += 1
    return "\n".join(out)


def _replace_metadata(content: str, total_enriched: int) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = []
    for line in content.split("\n"):
        if line.startswith(LAST_UPDATE_PREFIX):
            lines.append(f"{LAST_UPDATE_PREFIX} : {today}")
        elif line.startswith(TOTAL_ENRICHED_PREFIX):
            lines.append(f"{TOTAL_ENRICHED_PREFIX} : {total_enriched}")
        else:
            lines.append(line)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--liaprobe-root", type=Path, default=None)
    p.add_argument("--index-out", type=Path, default=None,
                   help="Override the ENRICHED_RULES.md output path "
                        "(default: committed dev tracking dir, R7).")
    args = p.parse_args(argv)

    root = (args.liaprobe_root or _resolve_liaprobe_root()).resolve()
    state_dir = root / "_alire/tracking/liaprobe-enrich-v2/runtime/enrich_state"
    index_md = (args.index_out or _resolve_index_path()).resolve()
    if not state_dir.exists():
        print(f"state_dir not found: {state_dir}", file=sys.stderr)
        return 2
    if not index_md.exists():
        print(f"ENRICHED_RULES.md not found: {index_md}", file=sys.stderr)
        return 2

    states = []
    for f in sorted(state_dir.glob("*.state.json")):
        try:
            with f.open(encoding="utf-8") as fp:
                states.append(json.load(fp))
        except (OSError, json.JSONDecodeError) as e:
            print(f"skip {f.name}: {e}", file=sys.stderr)

    content = index_md.read_text(encoding="utf-8")
    content = _replace_section(content, REGISTRY_HEADER, _summary_table(states, {"liaprobe": root}))
    content = _replace_section(content, LIFECYCLE_HEADER, _lifecycle_table(states))
    content = _replace_metadata(content, len(states))
    index_md.write_text(content, encoding="utf-8")
    print(f"updated {index_md} with {len(states)} enriched rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
