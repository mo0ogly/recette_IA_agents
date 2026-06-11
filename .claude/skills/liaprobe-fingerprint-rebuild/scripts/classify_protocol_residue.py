#!/usr/bin/env python3
"""c34 A29: classify the 61 rules without canonical_vendor into 3 buckets
and inject explicit classification markers in each rule.

Buckets:
- PROTOCOL: filename contains a known protocol token (POP3, SMTP, ...) AND
  rule.vendor is a junk meta-vendor (Various/Generic/Unknown). These are
  protocol fingerprints with no canonical vendor by design.
- JUNK_VENDOR: rule.vendor is in {Various, Generic, Unknown, Embedded, ""}
  but filename is NOT a protocol -- the rule lacks attribution by author.
- UNKNOWN_VENDOR: rule.vendor is a real-looking string but PG has no match.
  Future enrichment target.

Output: injects `_meta_enrichment.classification_c34` block in each rule.
- PROTOCOL + JUNK_VENDOR -> permanent_doubtful=True (no canonical)
- UNKNOWN_VENDOR -> pending_enrichment=True (queued for future c{N}+ cycles)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE = Path("/opt/lia-sec/liaprobe")
DEV = Path("/opt/lia-sec/dev")
TRACKING = DEV / "_alire/tracking/liaprobe-fingerprint-rebuild"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
DEFAULT_OUT = TRACKING / f"CLASSIFY_RESIDUE_{RUN_DATE}.json"

PROTOCOLS = {
    "MODBUS", "POP3", "SMTP", "TELNET", "VNC", "SOCKS5", "PJL", "NTRIP",
    "RTSPSVR", "RTSP", "SNMP", "LDAP", "SIP", "MQTT", "TFTP", "NFS",
    "NTP", "SSDP", "MDNS", "XMPP", "IMAP", "DNS", "BGP", "RDP", "BACNT",
    "ENIP",
}
JUNK_INPUTS = {"Various", "Generic", "Unknown", "Embedded", "embedded", "", None,
               "various", "multi-vendor"}


def classify(rule: dict, basename: str) -> tuple[str, str]:
    """Returns (bucket, reason)."""
    v = (rule.get("vendor") or "").strip()
    base = basename.replace(".json", "").upper()
    is_protocol_name = any(proto in base for proto in PROTOCOLS)

    if v in JUNK_INPUTS:
        if is_protocol_name:
            return ("PROTOCOL", f"protocol_fingerprint_no_vendor (rule.vendor={v!r} basename hints {base})")
        return ("JUNK_VENDOR", f"author_unattributed (rule.vendor={v!r} but product={rule.get('product')!r})")

    return ("UNKNOWN_VENDOR", f"real_vendor_no_pg_match (rule.vendor={v!r})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--rules-dir", type=Path, default=LIAPROBE / "patterns/lia")
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        ap.error("Specify --apply or --dry-run")

    rules: list[tuple[Path, dict]] = []
    for p in sorted(args.rules_dir.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        cv = (r.get("_meta_enrichment") or {}).get("canonical_vendor")
        if cv:
            continue
        rules.append((p, r))

    print(f"[INFO] residual rules (no canonical_vendor) : {len(rules)}")
    print(f"[INFO] mode                                 : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    results: list[dict] = []
    counts: dict[str, int] = {}
    for p, r in rules:
        bucket, reason = classify(r, p.name)
        permanent = bucket in ("PROTOCOL", "JUNK_VENDOR")
        result = {
            "basename": p.name,
            "rule_vendor": r.get("vendor"),
            "rule_product": r.get("product"),
            "bucket": bucket,
            "reason": reason,
            "permanent_doubtful": permanent,
            "pending_enrichment": not permanent,
        }
        results.append(result)
        counts[bucket] = counts.get(bucket, 0) + 1

        if not args.dry_run:
            meta = r.setdefault("_meta_enrichment", {})
            meta["classification_c34"] = {
                "date": NOW,
                "bucket": bucket,
                "reason": reason,
                "permanent_doubtful": permanent,
                "pending_enrichment": not permanent,
            }
            p.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")

        marker = "PERM" if permanent else "PEND"
        print(f"  [{bucket:14}] [{marker}] {p.name:30} {r.get('vendor')!r:25} -> {reason}")

    artifact = {
        "schema": "lia-classify-residue-v1",
        "generated_at": NOW,
        "rules_scanned": len(rules),
        "summary": counts,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("[SUMMARY]")
    for k in sorted(counts.keys()):
        print(f"  {k:<18}: {counts[k]}")
    print(f"\noutput: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
