#!/usr/bin/env python3
"""
build_default_creds_master.py -- Build sourced default_creds_master.json from
cached DefaultCreds-Cheat-Sheet.csv (Apache 2.0 / MIT licensed source).

Each entry tracks :
- source_url (original GitHub raw URL)
- source_sha256 (sha256 of cached CSV at fetch time)
- source_line (1-based line number in cached CSV)
- fetched_at (ISO 8601)

This permits replay : re-fetch URL, diff vs cached sha256, detect upstream change.

Usage:
    python3 build_default_creds_master.py \
        --cache _alire/tracking/liaprobe-enrich-v2/master_data/sources/defaultcreds_cheat_sheet/DefaultCreds-Cheat-Sheet.csv \
        --manifest _alire/tracking/liaprobe-enrich-v2/master_data/sources/defaultcreds_cheat_sheet/manifest.json \
        --out _alire/tracking/liaprobe-enrich-v2/master_data/default_creds_master.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Maps DefaultCreds-cheat-sheet productvendor strings to liaprobe_product_key
# Mapping is conservative (1 product per key, vendor:product canonical form)
PRODUCT_MAP = {
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path, required=True,
                   help="Path to cached DefaultCreds-Cheat-Sheet.csv")
    p.add_argument("--manifest", type=Path, required=True,
                   help="Path to source manifest.json (provides source_url + sha256)")
    p.add_argument("--out", type=Path, required=True,
                   help="Path to write default_creds_master.json")
    args = p.parse_args(argv)

    # Verify cached file integrity vs manifest
    if not args.cache.exists():
        print(f"cache not found: {args.cache}", file=sys.stderr)
        return 2
    if not args.manifest.exists():
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    actual_sha = hashlib.sha256(args.cache.read_bytes()).hexdigest()
    if actual_sha != manifest.get("sha256"):
        print(
            f"INTEGRITY FAIL: cache sha256 {actual_sha[:16]} != manifest "
            f"{manifest.get('sha256','')[:16]}",
            file=sys.stderr,
        )
        return 3

    source_url = manifest.get("source_url")
    source_sha = manifest.get("sha256")
    fetched_at = manifest.get("fetched_at")

    # Parse CSV
    products: dict[str, dict] = {}
    with args.cache.open(newline="", encoding="utf-8", errors="replace") as fp:
        reader = csv.reader(fp)
        header = next(reader)  # productvendor,username,password
        for line_num, row in enumerate(reader, start=2):
            if len(row) < 3:
                continue
            productvendor, username, password = row[0], row[1], row[2]
            key = PRODUCT_MAP.get(productvendor)
            if key is None:
                continue
            entry = products.setdefault(key, {
                "default_credentials": [],
                "source": {
                    "url": source_url,
                    "sha256": source_sha,
                    "fetched_at": fetched_at,
                    "license": manifest.get("license"),
                    "productvendor_string": productvendor,
                },
            })
            cred = {
                "username": username if username and username != "<blank>" else None,
                "password": password if password and password != "<blank>" else None,
                "source_line": line_num,
                "source_productvendor": productvendor,
            }
            entry["default_credentials"].append(cred)

    out = {
        "$schema": "lia-default-creds-master-v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_manifest": str(args.manifest),
        "products_count": len(products),
        "total_credentials": sum(len(p["default_credentials"]) for p in products.values()),
        "products": products,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"  products: {out['products_count']}")
    print(f"  total credentials: {out['total_credentials']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
