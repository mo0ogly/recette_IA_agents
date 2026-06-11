#!/usr/bin/env python3
"""
build_default_creds_master_v2.py -- Build sourced default_creds_master.json from
3 cached authoritative sources (DefaultCreds-cheat-sheet + SecLists + BetterDefaultPasslist).

Each entry tracks :
- source_id (defaultcreds_cheat_sheet | seclists_default_passwords | betterdefaultpasslist)
- source_url (original URL)
- source_sha256 (sha256 of cached file at fetch time)
- source_line (1-based line number in cached file)
- source_file (relative path to cached file)
- fetched_at (ISO 8601)

Permits replay : re-fetch URL, diff vs cached sha256, detect upstream change.

Usage:
    python3 build_default_creds_master_v2.py --root <liaprobe_root> --out <output>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# --- Source 1 : DefaultCreds-cheat-sheet (productvendor -> liaprobe_product_key) ---
DEFAULTCREDS_PRODUCT_MAP = {
    "Jenkins (web)": "jenkins/jenkins",
    "Kibana (web)": "elastic/kibana",
    "Elasticsearch (web)": "elastic/elasticsearch",
    "elasticsearch (web)": "elastic/elasticsearch",
    "Grafana (general)": "grafana/grafana",
    "Mongodb noauth (mongodb)": "mongodb/mongodb",
    "Redis (redis)": "redis/redis",
    "SonarQube (web)": "sonarsource/sonarqube",
    "Gitlab": "gitlab/gitlab",
    "Apache Tomcat Host Manager (web)": "apache/tomcat",
    "Nexus Repository Manager (web)": "sonatype/nexus_repository_manager",
    "Artifactory": "jfrog/artifactory",
    "RabbitMQ": "rabbitmq/rabbitmq",
    "MinIO": "minio/minio",
    "Couchdb": "couchdb/couchdb",
    "InfluxDB (web)": "influxdata/influxdb",
}

# --- Source 2 : SecLists default-passwords.csv (Vendor -> liaprobe_product_key) ---
# SecLists is HUGE -- map only top-priority products, fall back to vendor-only
SECLISTS_VENDOR_MAP = {
    "3Com": "3com/generic",
    "APC": "apc/generic",
    "Cisco": "cisco/generic",
    "Citrix": "citrix/generic",
    "D-Link": "dlink/generic",
    "F5 Networks": "f5/generic",
    "Fortinet": "fortinet/generic",
    "HP": "hp/generic",
    "Huawei Technologies": "huawei/generic",
    "IBM": "ibm/generic",
    "Juniper Networks": "juniper/generic",
    "Linksys": "linksys/generic",
    "Netgear": "netgear/generic",
    "Oracle": "oracle/generic",
    "SonicWall": "sonicwall/generic",
    "Symantec": "symantec/generic",
    "TP-Link Technologies Co., Ltd.": "tp-link/generic",
    "VMware": "vmware/generic",
    "Zyxel": "zyxel/generic",
}

# --- Source 3 : BetterDefaultPasslist per-protocol files -> products ---
# username:password format ; map filename to product_key
BDP_PROTOCOL_MAP = {
    "mysql.txt": "mysql/mysql",
    "postgres.txt": "postgresql/postgresql",
    "mssql.txt": "microsoft/sql_server",
    "oracle.txt": "oracle/database",
    "db2.txt": "ibm/db2",
    "tomcat.txt": "apache/tomcat",
    "ssh.txt": "openssh/openssh",
    "telnet.txt": "generic/telnet",
    "ftp.txt": "generic/ftp",
    "vnc.txt": "generic/vnc",
    "windows.txt": "microsoft/windows",
}


def _verify_cache(cached_path: Path, expected_sha: str) -> None:
    actual = hashlib.sha256(cached_path.read_bytes()).hexdigest()
    if actual != expected_sha:
        raise RuntimeError(
            f"INTEGRITY FAIL: {cached_path.name} sha {actual[:16]} != "
            f"manifest {expected_sha[:16]}"
        )


def _norm_value(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    if not s:
        return None
    if s.lower() in ("<blank>", "(blank)", "(empty)", "n/a", "<n/a>"):
        return None
    return s


def parse_defaultcreds(root: Path, products: dict) -> int:
    src = root / "_alire/tracking/liaprobe-enrich-v2/master_data/sources/defaultcreds_cheat_sheet"
    csv_path = src / "DefaultCreds-Cheat-Sheet.csv"
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    _verify_cache(csv_path, manifest["sha256"])

    count = 0
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as fp:
        reader = csv.reader(fp)
        next(reader)
        for line_num, row in enumerate(reader, start=2):
            if len(row) < 3:
                continue
            pv, u, p = row[0], row[1], row[2]
            key = DEFAULTCREDS_PRODUCT_MAP.get(pv)
            if not key:
                continue
            products[key].append({
                "username": _norm_value(u),
                "password": _norm_value(p),
                "source_id": "defaultcreds_cheat_sheet",
                "source_url": manifest["source_url"],
                "source_sha256": manifest["sha256"],
                "source_file": "defaultcreds_cheat_sheet/DefaultCreds-Cheat-Sheet.csv",
                "source_line": line_num,
                "source_match_string": pv,
            })
            count += 1
    return count


def parse_seclists(root: Path, products: dict) -> int:
    src = root / "_alire/tracking/liaprobe-enrich-v2/master_data/sources/seclists"
    csv_path = src / "default-passwords.csv"
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    file_meta = manifest["files"]["default-passwords.csv"]
    _verify_cache(csv_path, file_meta["sha256"])

    count = 0
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as fp:
        reader = csv.reader(fp)
        next(reader)  # Vendor,Username,Password,Comments
        for line_num, row in enumerate(reader, start=2):
            if len(row) < 3:
                continue
            vendor, u, p = row[0], row[1], row[2]
            key = SECLISTS_VENDOR_MAP.get(vendor)
            if not key:
                continue
            products[key].append({
                "username": _norm_value(u),
                "password": _norm_value(p),
                "source_id": "seclists_default_passwords",
                "source_url": file_meta["url"],
                "source_sha256": file_meta["sha256"],
                "source_file": "seclists/default-passwords.csv",
                "source_line": line_num,
                "source_match_string": vendor,
                "source_comment": row[3] if len(row) > 3 else None,
            })
            count += 1
    return count


def parse_bdp(root: Path, products: dict) -> int:
    src = root / "_alire/tracking/liaprobe-enrich-v2/master_data/sources/betterdefaultpasslist"
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))

    count = 0
    for fname, file_meta in manifest["files"].items():
        key = BDP_PROTOCOL_MAP.get(fname)
        if not key:
            continue
        cached = src / fname
        _verify_cache(cached, file_meta["sha256"])
        with cached.open(encoding="utf-8", errors="replace") as fp:
            for line_num, line in enumerate(fp, start=1):
                line = line.rstrip("\r\n")
                if not line or line.startswith("#"):
                    continue
                if ":" not in line:
                    continue
                u, p = line.split(":", 1)
                products[key].append({
                    "username": _norm_value(u),
                    "password": _norm_value(p),
                    "source_id": "betterdefaultpasslist",
                    "source_url": file_meta["url"],
                    "source_sha256": file_meta["sha256"],
                    "source_file": f"betterdefaultpasslist/{fname}",
                    "source_line": line_num,
                    "source_match_string": fname,
                })
                count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True,
                   help="LiaProbe root (contains _alire/tracking/liaprobe-enrich-v2/...)")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)

    root = args.root.resolve()
    products: dict[str, list[dict]] = defaultdict(list)

    counts = {
        "defaultcreds_cheat_sheet": parse_defaultcreds(root, products),
        "seclists_default_passwords": parse_seclists(root, products),
        "betterdefaultpasslist": parse_bdp(root, products),
    }

    out = {
        "$schema": "lia-default-creds-master-v2",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "products_count": len(products),
        "total_credentials": sum(len(v) for v in products.values()),
        "credentials_by_source": counts,
        "products": dict(sorted(products.items())),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"  products: {out['products_count']}")
    print(f"  total credentials: {out['total_credentials']}")
    for src, n in counts.items():
        print(f"  {src}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
