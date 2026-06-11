#!/usr/bin/env python3
# merge_loser_matchers.py
#
# c26 ST1-bis: absorb banner_matchers + probes from archived MERGE losers
# into their corresponding winners. Recovers detection coverage lost when
# losers were moved to _archive_c26/ (89 CORRECT -> MISS regression).
#
# Reads triage decisions from apply_collision_triage.py TRIAGE list.
# For each MERGE entry:
#   - Load winner rule (now at <winner_target>)
#   - For each archived loser (in _archive_c26/<loser>): load
#   - Append unique banner_matchers (dedupe by regex string)
#   - Append unique probes (dedupe by send_hex or matchers signature)
#   - Update winner audit block with absorbed_matchers_from_losers list
#
# Conservative dedupe: by literal regex string for matchers, by probe
# send_hex (or probe.name) for probes.

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
DEV_DIR = Path("/opt/lia-sec/dev")
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c26/matcher_merge_backup"
ARCHIVE_SUBDIR = "_archive_c26"
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
PASS_ID = f"{RUN_DATE}_apex_c26_merge_loser_matchers"

# Mirror of apply_collision_triage.py MERGE entries that need matcher
# absorption. (winner_target, [loser_basename, ...])
MERGE_PAIRS: list[tuple[str, list[str]]] = [
    ("Apache_ActiveMQ.json", ["ACTIVEMQ.json"]),
    ("Citrix_Gateway.json", ["CITRXGW.json"]),
    ("Microsoft_Exchange_Server.json", ["EXCHG.json"]),
    ("Proxmox_Virtual_Environment.json", ["PVEWEB.json"]),
    ("Splunk.json", ["SPLU.json"]),
    ("Twistedmatrix_Twisted.json", ["TWISTEDWEB.json"]),
    ("Nlnetlabs_Unbound.json", ["UNBND.json"]),
    ("Varnish-Software_Varnish_Cache.json", ["VRNSH.json"]),
    ("Apache_Tomcat.json", ["TOMCAT.json", "TOMCM.json"]),
    ("Amazon_Echo.json", ["AMZECHO.json"]),
    ("Oracle_Weblogic_Server.json", ["WLOGC.json", "WLOGC_HTTP.json"]),
    # IBM_Lotus_Domino: LOTDOM was a true dup of LDOMINO -> merge its matchers too
    ("IBM_Lotus_Domino.json", ["LOTDOM.json"]),
]


def _matcher_sig(m: dict[str, Any]) -> str:
    # Stable signature: target + match_type + value/regex
    key_fields = ("target", "match_type", "value", "regex")
    repr_str = "|".join(str(m.get(k, "")) for k in key_fields)
    return hashlib.sha256(repr_str.encode("utf-8")).hexdigest()[:16]


def _probe_sig(p: dict[str, Any]) -> str:
    # Stable signature: name + send_hex + send + protocol + ports
    parts = [
        p.get("name", ""),
        p.get("send_hex", ""),
        p.get("send", ""),
        p.get("protocol", ""),
        ",".join(str(x) for x in sorted(p.get("ports", []) or [])),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _backup(p: Path) -> None:
    if not p.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / p.name
    if not target.exists():
        shutil.copy2(p, target)


def merge_one(winner_target: str, losers: list[str], dry: bool) -> list[str]:
    out: list[str] = []
    winner_path = LIAPROBE_DIR / "patterns/lia" / winner_target
    if not winner_path.exists():
        return [f"MISSING_WINNER {winner_target}"]
    try:
        winner = json.loads(winner_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"READ_FAIL_WINNER {winner_target}: {exc}"]

    winner_matchers = winner.get("banner_matchers") or []
    winner_probes = winner.get("probes") or []
    existing_matcher_sigs = {_matcher_sig(m) for m in winner_matchers}
    existing_probe_sigs = {_probe_sig(p) for p in winner_probes}

    absorbed: list[dict[str, Any]] = []
    for loser_basename in losers:
        loser_path = LIAPROBE_DIR / "patterns/lia" / ARCHIVE_SUBDIR / loser_basename
        if not loser_path.exists():
            out.append(f"MISSING_LOSER {loser_basename}")
            continue
        try:
            loser = json.loads(loser_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            out.append(f"READ_FAIL_LOSER {loser_basename}: {exc}")
            continue

        added_matchers = 0
        for m in (loser.get("banner_matchers") or []):
            sig = _matcher_sig(m)
            if sig in existing_matcher_sigs:
                continue
            winner_matchers.append(m)
            existing_matcher_sigs.add(sig)
            added_matchers += 1

        added_probes = 0
        for p in (loser.get("probes") or []):
            sig = _probe_sig(p)
            if sig in existing_probe_sigs:
                continue
            winner_probes.append(p)
            existing_probe_sigs.add(sig)
            added_probes += 1

        absorbed.append({
            "loser_basename": loser_basename,
            "matchers_added": added_matchers,
            "probes_added": added_probes,
            "loser_total_matchers": len(loser.get("banner_matchers") or []),
            "loser_total_probes": len(loser.get("probes") or []),
        })
        out.append(f"  {loser_basename}: +{added_matchers}m +{added_probes}p")

    if dry:
        out.insert(0, f"DRY-MERGE-INTO {winner_target}")
        return out

    winner["banner_matchers"] = winner_matchers
    winner["probes"] = winner_probes
    auth = winner.setdefault("_lia_independent_authoring", {})
    auth.setdefault("collision_triage_c26", {})["matcher_absorption"] = {
        "date": NOW_ISO,
        "absorbed_from_losers": absorbed,
        "winner_total_matchers_after": len(winner_matchers),
        "winner_total_probes_after": len(winner_probes),
        "marked_by": PASS_ID,
    }
    _backup(winner_path)
    winner_path.write_text(json.dumps(winner, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    out.insert(0, f"MERGED-INTO {winner_target}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        ap.error("Specify --apply or --dry-run")

    print(f"[INFO] merge pairs        : {len(MERGE_PAIRS)}")
    print(f"[INFO] mode               : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    counts: dict[str, int] = {}
    for winner, losers in MERGE_PAIRS:
        lines = merge_one(winner, losers, args.dry_run)
        for line in lines:
            print(line)
            key = line.lstrip().split(" ", 1)[0]
            counts[key] = counts.get(key, 0) + 1
        print()

    print("[SUMMARY]")
    for k in sorted(counts.keys()):
        print(f"  {k:<24}: {counts[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
