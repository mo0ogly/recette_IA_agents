#!/usr/bin/env python3
# apply_collision_triage.py
#
# Apply human-decided triage for the 19 collisions found in
# RENAME_PROPOSALS_<DATE>.json. Three action types:
#
#   MERGE: archive_dir = patterns/lia/_archive_c26/{loser}.json (preserves
#          history via git mv), winner renamed to canonical basename + audit.
#   SPLIT: each rule renamed with a disambiguator suffix that reflects
#          its sub-product (e.g. Argoproj_Argo_Cd.json + Argoproj_Argo_Cd_Notifications.json).
#   REVENDOR: rule queued to NEXT_ENRICH_QUEUE.md for re-resolution
#             (canonical_vendor wrong, needs vendor sync re-pass).
#
# Each action injects an audit block under _lia_independent_authoring:
#   - collision_triage_c26 = {action, decided_at, reason, winner|loser}
#   - filename_rename_c26  = filename_rename_c{N} format (see c25)
#
# Decisions live in a hardcoded TRIAGE list below. No autonomic guessing.

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
DEV_DIR = Path("/opt/lia-sec/dev")
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c26/triage_backup"
ARCHIVE_SUBDIR = "_archive_c26"
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
CYCLE = "c26"
PASS_ID = f"{RUN_DATE}_apex_{CYCLE}_collision_triage"

# Each entry describes one collision group + the manual decision.
# Required keys:
#   group           : collision name (matches RENAME_PROPOSALS_*.json collisions key)
#   action          : "MERGE" | "SPLIT" | "REVENDOR"
#   reason          : short human-readable rationale
#
# For MERGE:
#   winner          : current basename to keep (will be renamed to canonical)
#   winner_target   : canonical basename for winner
#   losers          : list of current basenames to archive
#
# For SPLIT:
#   members         : list of {current, target, sub_product_label}
#                     where target is the disambiguated canonical basename
#
# For REVENDOR:
#   members         : list of current basenames to queue for re-vendor
#   note            : why canonical is wrong

TRIAGE: list[dict[str, Any]] = [
    {
        "group": "Apache_ActiveMQ.json",
        "action": "MERGE",
        "reason": "ACTMQ has 1 matcher + 2 probes (richer); ACTIVEMQ has 1 matcher, 0 probes (subset). Same product.",
        "winner": "ACTMQ.json",
        "winner_target": "Apache_ActiveMQ.json",
        "losers": ["ACTIVEMQ.json"],
    },
    {
        "group": "Argoproj_Argo_Cd.json",
        "action": "SPLIT",
        "reason": "ARCD = ArgoCD main server. ARCDN = ArgoCD Notifications Controller (distinct sub-product).",
        "members": [
            {"current": "ARCD.json", "target": "Argoproj_Argo_Cd.json",
             "sub_product_label": "Argo CD"},
            {"current": "ARCDN.json", "target": "Argoproj_Argo_Cd_Notifications.json",
             "sub_product_label": "Argo CD Notifications Controller"},
        ],
    },
    {
        "group": "Citrix_Gateway.json",
        "action": "MERGE",
        "reason": "CITGW has 3 matchers (richer); CITRXGW has 1 matcher (subset). Same product.",
        "winner": "CITGW.json",
        "winner_target": "Citrix_Gateway.json",
        "losers": ["CITRXGW.json"],
    },
    {
        "group": "Microsoft_Exchange_Server.json",
        "action": "MERGE",
        "reason": "EXCHANGE has 3 banner_matchers (richer); EXCHG has 4 probes but 0 matchers (different detection style, same product). Keep EXCHANGE as it has higher-trust banner detection.",
        "winner": "EXCHANGE.json",
        "winner_target": "Microsoft_Exchange_Server.json",
        "losers": ["EXCHG.json"],
    },
    {
        "group": "Proxmox_Virtual_Environment.json",
        "action": "MERGE",
        "reason": "PROXMOX has 2 matchers + 3 probes (richer). PVEWEB has 1 matcher + 0 probes. Same product.",
        "winner": "PROXMOX.json",
        "winner_target": "Proxmox_Virtual_Environment.json",
        "losers": ["PVEWEB.json"],
    },
    {
        "group": "SAP_Netweaver.json",
        "action": "SPLIT",
        "reason": "SAP = SAP Application Server (Native Protocols). SAPRTR = SAP Network Interface Router (NIRouter, distinct component).",
        "members": [
            {"current": "SAP.json", "target": "SAP_Netweaver.json",
             "sub_product_label": "SAP Application Server"},
            {"current": "SAPRTR.json", "target": "SAP_Netweaver_Router.json",
             "sub_product_label": "SAP Netweaver Router"},
        ],
    },
    {
        "group": "Splunk.json",
        "action": "MERGE",
        "reason": "SPLUNK has 1 matcher (banner detection). SPLU has 1 probe (subset). Same product.",
        "winner": "SPLUNK.json",
        "winner_target": "Splunk.json",
        "losers": ["SPLU.json"],
    },
    {
        "group": "Traefik.json",
        "action": "SPLIT",
        "reason": "TRAEF = Traefik proxy (main service). TRFIK = Traefik Dashboard (web UI, distinct).",
        "members": [
            {"current": "TRAEF.json", "target": "Traefik.json",
             "sub_product_label": "Traefik"},
            {"current": "TRFIK.json", "target": "Traefik_Dashboard.json",
             "sub_product_label": "Traefik Dashboard"},
        ],
    },
    {
        "group": "Twistedmatrix_Twisted.json",
        "action": "MERGE",
        "reason": "TWSTW has 1 matcher + 1 probe (richer). TWISTEDWEB has 1 matcher, 0 probes (subset). Same product.",
        "winner": "TWSTW.json",
        "winner_target": "Twistedmatrix_Twisted.json",
        "losers": ["TWISTEDWEB.json"],
    },
    {
        "group": "Nlnetlabs_Unbound.json",
        "action": "MERGE",
        "reason": "UNBOUND has 1 matcher (canonical name). UNBND has 1 matcher (legacy stem). Same content. Keep UNBOUND.",
        "winner": "UNBOUND.json",
        "winner_target": "Nlnetlabs_Unbound.json",
        "losers": ["UNBND.json"],
    },
    {
        "group": "Varnish-Software_Varnish_Cache.json",
        "action": "MERGE",
        "reason": "VARNISH has 2 matchers (richer). VRNSH has 0 matchers + 1 probe (subset). Same product.",
        "winner": "VARNISH.json",
        "winner_target": "Varnish-Software_Varnish_Cache.json",
        "losers": ["VRNSH.json"],
    },
    {
        "group": "Apache_Tomcat.json",
        "action": "MERGE",
        "reason": "TOMC has 2 matchers + 1 probe (richest). TOMCAT 2 matchers, 0 probes. TOMCM ~ similar to TOMCAT. Same product. Keep TOMC.",
        "winner": "TOMC.json",
        "winner_target": "Apache_Tomcat.json",
        "losers": ["TOMCAT.json", "TOMCM.json"],
    },
    {
        "group": "Amazon_Echo.json",
        "action": "MERGE",
        "reason": "ECHO has 3 matchers + 5 probes (richest). AMZECHO has 0 matchers + 1 probe (subset). Same product.",
        "winner": "ECHO.json",
        "winner_target": "Amazon_Echo.json",
        "losers": ["AMZECHO.json"],
    },
    {
        "group": "Checkpoint_Check_Point.json",
        "action": "REVENDOR",
        "members": ["CPSVN.json"],
        "note": "CPSVN.json detects 'SVN foundation' (Apache Subversion-related), NOT Checkpoint. Wrong canonical_vendor resolution. Queue for vendor sync re-pass. CHKPT (Check Point Gaia) stays as Checkpoint_Gaia.json (rename via standard path after CPSVN is re-vendored).",
        "reason": "CPSVN wrong canonical_vendor (detects SVN foundation product, not Checkpoint).",
    },
    {
        "group": "Cisco_Cisco_IOS.json",
        "action": "SPLIT",
        "reason": "CISCOIOS = Cisco IOS generic banner. CISCO_SSH = Cisco IOS SSH banner-specific subset.",
        "members": [
            {"current": "CISCOIOS.json", "target": "Cisco_Cisco_IOS.json",
             "sub_product_label": "Cisco IOS"},
            {"current": "CISCO_SSH.json", "target": "Cisco_Cisco_IOS_SSH.json",
             "sub_product_label": "Cisco IOS (SSH)"},
        ],
    },
    {
        "group": "MinIO.json",
        "action": "SPLIT",
        "reason": "MINI = MinIO S3 server (main API). MINIOCONSOLE = MinIO Console (web admin UI, distinct).",
        "members": [
            {"current": "MINI.json", "target": "MinIO.json",
             "sub_product_label": "MinIO"},
            {"current": "MINIOCONSOLE.json", "target": "MinIO_Console.json",
             "sub_product_label": "MinIO Console"},
        ],
    },
    {
        "group": "Oracle_Weblogic_Server.json",
        "action": "MERGE",
        "reason": "WEBLOGIC has banner_matchers (richest). WLOGC + WLOGC_HTTP are subsets/variants. Same product.",
        "winner": "WEBLOGIC.json",
        "winner_target": "Oracle_Weblogic_Server.json",
        "losers": ["WLOGC.json", "WLOGC_HTTP.json"],
    },
    {
        "group": "IBM_Lotus_Domino.json",
        "action": "SPLIT",
        "reason": "IBMNOTES = IBM Lotus Notes (mail client, ports POP/IMAP). LDOMINO + LOTDOM = IBM Lotus Domino (web server, ports HTTP). Two distinct products.",
        "members": [
            {"current": "IBMNOTES.json", "target": "IBM_Lotus_Notes.json",
             "sub_product_label": "IBM Lotus Notes (Mail)"},
            {"current": "LDOMINO.json", "target": "IBM_Lotus_Domino.json",
             "sub_product_label": "IBM Lotus Domino"},
            {"current": "LOTDOM.json", "target": None,
             "sub_product_label": "IBM Lotus Domino (duplicate of LDOMINO)",
             "merge_into": "LDOMINO.json"},
        ],
    },
    {
        "group": "Amd_Epyc_Embedded_7252.json",
        "action": "REVENDOR",
        "members": ["H264DVR.json", "UCHTTPD.json"],
        "note": "Both files were fuzzy-resolved to AMD Epyc CPU via product_ilike_dominant. H264DVR fingerprints an embedded video DVR (cameras), UCHTTPD fingerprints the uc-httpd embedded webserver (router firmware). Neither relates to AMD. Queue for vendor sync re-pass with stricter alias_exact preference.",
        "reason": "Wrong canonical_vendor (AMD Epyc CPU != DVR firmware / embedded webserver).",
    },
]


def _backup(src: Path) -> None:
    if not src.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    bk = BACKUP_DIR / src.name
    if not bk.exists():
        shutil.copy2(src, bk)


def _git_mv(src: Path, dst: Path) -> tuple[bool, str]:
    if dst.exists():
        return False, f"DEST_EXISTS {dst.name}"
    cmd = ["git", "-C", str(LIAPROBE_DIR), "mv",
           str(src.relative_to(LIAPROBE_DIR)), str(dst.relative_to(LIAPROBE_DIR))]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10)
    except subprocess.CalledProcessError as exc:
        return False, f"GIT_MV_FAIL {src.name}: {exc.stderr.strip()}"
    return True, ""


def _patch_audit(rule_path: Path, audit_block: dict[str, Any], audit_key: str,
                 source_file_new: str | None) -> tuple[bool, str]:
    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"READ_FAIL {rule_path.name}: {exc}"
    auth = rule.setdefault("_lia_independent_authoring", {})
    auth[audit_key] = audit_block
    if source_file_new:
        src_obj = rule.setdefault("source", {})
        src_obj["file"] = source_file_new
    rule_path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    return True, ""


def _apply_merge(decision: dict[str, Any], dry: bool) -> list[str]:
    out: list[str] = []
    winner_path = LIAPROBE_DIR / "patterns/lia" / decision["winner"]
    target_path = LIAPROBE_DIR / "patterns/lia" / decision["winner_target"]

    if dry:
        out.append(f"DRY-MERGE winner={decision['winner']} -> {decision['winner_target']}")
        for loser in decision["losers"]:
            out.append(f"  DRY-ARCHIVE {loser} -> patterns/lia/{ARCHIVE_SUBDIR}/{loser}")
        return out

    if not winner_path.exists():
        return [f"MISSING_WINNER {decision['winner']}"]
    _backup(winner_path)
    ok, err = _git_mv(winner_path, target_path)
    if not ok:
        return [err]
    audit = {
        "date": NOW_ISO,
        "action": "MERGE",
        "role": "winner",
        "from_basename": decision["winner"],
        "to_basename": decision["winner_target"],
        "merged_with": decision["losers"],
        "reason": decision["reason"],
        "marked_by": PASS_ID,
    }
    ok, err = _patch_audit(target_path, audit, "collision_triage_c26",
                           decision["winner_target"])
    if not ok:
        return [err]
    out.append(f"MERGED_WINNER {decision['winner']} -> {decision['winner_target']}")

    archive_dir = LIAPROBE_DIR / "patterns/lia" / ARCHIVE_SUBDIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    for loser in decision["losers"]:
        loser_path = LIAPROBE_DIR / "patterns/lia" / loser
        if not loser_path.exists():
            out.append(f"  MISSING_LOSER {loser}")
            continue
        _backup(loser_path)
        archive_target = archive_dir / loser
        ok, err = _git_mv(loser_path, archive_target)
        if not ok:
            out.append(f"  {err}")
            continue
        audit_loser = {
            "date": NOW_ISO,
            "action": "MERGE",
            "role": "loser_archived",
            "from_basename": loser,
            "archive_path": str(archive_target.relative_to(LIAPROBE_DIR)),
            "winner": decision["winner_target"],
            "reason": decision["reason"],
            "marked_by": PASS_ID,
        }
        ok, err = _patch_audit(archive_target, audit_loser,
                               "collision_triage_c26", archive_target.name)
        if not ok:
            out.append(f"  {err}")
            continue
        out.append(f"  ARCHIVED {loser} -> {ARCHIVE_SUBDIR}/{loser}")
    return out


def _apply_split(decision: dict[str, Any], dry: bool) -> list[str]:
    out: list[str] = []
    for m in decision["members"]:
        cur_path = LIAPROBE_DIR / "patterns/lia" / m["current"]
        if "merge_into" in m:
            if dry:
                out.append(f"DRY-SPLIT-MERGE {m['current']} -> archive (dup of {m['merge_into']})")
                continue
            if not cur_path.exists():
                out.append(f"MISSING {m['current']}")
                continue
            _backup(cur_path)
            archive_dir = LIAPROBE_DIR / "patterns/lia" / ARCHIVE_SUBDIR
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_target = archive_dir / m["current"]
            ok, err = _git_mv(cur_path, archive_target)
            if not ok:
                out.append(err)
                continue
            audit_dup = {
                "date": NOW_ISO,
                "action": "SPLIT_MERGE",
                "role": "duplicate_archived",
                "from_basename": m["current"],
                "archive_path": str(archive_target.relative_to(LIAPROBE_DIR)),
                "duplicate_of": m["merge_into"],
                "reason": decision["reason"],
                "marked_by": PASS_ID,
            }
            _patch_audit(archive_target, audit_dup, "collision_triage_c26", archive_target.name)
            out.append(f"ARCHIVED_DUP {m['current']} (== {m['merge_into']})")
            continue

        target = m["target"]
        target_path = LIAPROBE_DIR / "patterns/lia" / target
        if dry:
            out.append(f"DRY-SPLIT {m['current']} -> {target} (sub: {m['sub_product_label']})")
            continue
        if not cur_path.exists():
            out.append(f"MISSING {m['current']}")
            continue
        _backup(cur_path)
        ok, err = _git_mv(cur_path, target_path)
        if not ok:
            out.append(err)
            continue
        audit_split = {
            "date": NOW_ISO,
            "action": "SPLIT",
            "role": "sub_product",
            "from_basename": m["current"],
            "to_basename": target,
            "sub_product_label": m["sub_product_label"],
            "collision_group": decision["group"],
            "reason": decision["reason"],
            "marked_by": PASS_ID,
        }
        ok, err = _patch_audit(target_path, audit_split, "collision_triage_c26", target)
        if not ok:
            out.append(err)
            continue
        out.append(f"SPLIT {m['current']} -> {target}")
    return out


def _apply_revendor(decision: dict[str, Any], dry: bool) -> list[str]:
    # REVENDOR action does NOT touch files. It records the decision in
    # each rule's audit block and queues them for vendor-sync re-pass
    # (via NEXT_ENRICH_QUEUE.md, manually appended by the operator).
    out: list[str] = []
    for basename in decision["members"]:
        cur_path = LIAPROBE_DIR / "patterns/lia" / basename
        if dry:
            out.append(f"DRY-REVENDOR {basename} (queue for re-vendor)")
            continue
        if not cur_path.exists():
            out.append(f"MISSING {basename}")
            continue
        _backup(cur_path)
        audit = {
            "date": NOW_ISO,
            "action": "REVENDOR",
            "current_basename": basename,
            "collision_group": decision["group"],
            "reason": decision["reason"],
            "note": decision["note"],
            "queue_target": "NEXT_ENRICH_QUEUE.md (vendor_sync re-pass with stricter alias_exact)",
            "marked_by": PASS_ID,
        }
        ok, err = _patch_audit(cur_path, audit, "collision_triage_c26", basename)
        if not ok:
            out.append(err)
            continue
        out.append(f"QUEUED_REVENDOR {basename}")
    return out


def _run_recette_onyphe(out_path: Path) -> tuple[bool, str]:
    """
    Run bin/recette-onyphe in LIAPROBE_DIR and capture JSON verdicts to out_path.
    Returns (ok, message).
    """
    binary = LIAPROBE_DIR / "bin/recette-onyphe"
    if not binary.exists():
        return False, f"missing binary: {binary} (run `make build` in liaprobe)"
    try:
        result = subprocess.run(
            [str(binary), "-output", str(out_path)],
            cwd=str(LIAPROBE_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, "recette-onyphe timeout (600s)"
    if result.returncode != 0:
        return False, f"recette-onyphe exit {result.returncode}: {result.stderr[:200]}"
    if not out_path.exists():
        return False, f"recette-onyphe produced no output: {out_path}"
    return True, str(out_path)


def _run_audit_coverage(pre: Path, post: Path) -> tuple[int, str]:
    """
    Invoke audit_merge_coverage.py with the captured pre+post snapshots.
    Returns (exit_code, summary_string). Exit code 1 if lost_correct_banners > 0.
    """
    audit_script = Path(__file__).parent / "audit_merge_coverage.py"
    audit_out = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild" / f"MERGE_COVERAGE_AUDIT_{RUN_DATE}.json"
    result = subprocess.run(
        [sys.executable, str(audit_script), "--pre", str(pre), "--post", str(post), "--out", str(audit_out)],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        return result.returncode, f"audit script exit {result.returncode}"
    if not audit_out.exists():
        return 2, "audit produced no JSON"
    audit = json.loads(audit_out.read_text(encoding="utf-8"))
    lost = audit.get("summary", {}).get("lost_correct_banners", 0)
    net = audit.get("summary", {}).get("net_delta_correct", 0)
    return (1 if lost > 0 else 0), f"lost={lost} net_delta_CORRECT={net} output={audit_out}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--audit-coverage",
        action="store_true",
        help="Capture engine pre/post snapshots and run audit_merge_coverage.py. "
             "Requires bin/recette-onyphe present in /opt/lia-sec/liaprobe. "
             "Exits non-zero if any CORRECT banner lost. APPLY mode only.",
    )
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        ap.error("Specify --apply or --dry-run")
    if args.audit_coverage and args.dry_run:
        ap.error("--audit-coverage requires --apply (dry-run does not touch files)")

    print(f"[INFO] triage entries     : {len(TRIAGE)}")
    print(f"[INFO] mode               : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print(f"[INFO] archive subdir     : patterns/lia/{ARCHIVE_SUBDIR}/")
    print(f"[INFO] backup dir         : {BACKUP_DIR}")
    print(f"[INFO] audit-coverage     : {args.audit_coverage}")
    print()

    pre_snapshot: Path | None = None
    if args.audit_coverage:
        pre_snapshot = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild" / f"COLLISION_TRIAGE_PRE_{RUN_DATE}.json"
        print(f"[STEP] capturing engine pre-snapshot -> {pre_snapshot}")
        ok, msg = _run_recette_onyphe(pre_snapshot)
        if not ok:
            print(f"[FATAL] pre-snapshot capture failed: {msg}")
            return 3
        print(f"[STEP] pre-snapshot OK: {msg}")
        print()

    counts: dict[str, int] = {}
    for d in TRIAGE:
        print(f"=== {d['group']} ({d['action']}) ===")
        if d["action"] == "MERGE":
            lines = _apply_merge(d, args.dry_run)
        elif d["action"] == "SPLIT":
            lines = _apply_split(d, args.dry_run)
        elif d["action"] == "REVENDOR":
            lines = _apply_revendor(d, args.dry_run)
        else:
            lines = [f"UNKNOWN_ACTION {d['action']}"]
        for line in lines:
            print(f"  {line}")
            key = line.lstrip().split(" ", 1)[0]
            counts[key] = counts.get(key, 0) + 1

    print("\n[SUMMARY]")
    for k in sorted(counts.keys()):
        print(f"  {k:<24}: {counts[k]}")

    if args.audit_coverage and pre_snapshot is not None:
        post_snapshot = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild" / f"COLLISION_TRIAGE_POST_{RUN_DATE}.json"
        print(f"\n[STEP] capturing engine post-snapshot -> {post_snapshot}")
        ok, msg = _run_recette_onyphe(post_snapshot)
        if not ok:
            print(f"[FATAL] post-snapshot capture failed: {msg}")
            return 3
        print(f"[STEP] post-snapshot OK: {msg}")
        print(f"\n[STEP] running audit_merge_coverage.py")
        audit_rc, audit_msg = _run_audit_coverage(pre_snapshot, post_snapshot)
        print(f"[AUDIT] {audit_msg}")
        if audit_rc != 0:
            print(f"[AUDIT] FAIL -- coverage loss detected, exit {audit_rc}")
            return audit_rc
        print(f"[AUDIT] PASS -- no CORRECT banner lost")

    return 0


if __name__ == "__main__":
    sys.exit(main())
