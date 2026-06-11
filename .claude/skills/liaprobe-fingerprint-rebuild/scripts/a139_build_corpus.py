#!/usr/bin/env python3
# a139_build_corpus.py
#
# A139 -- READ-ONLY. Build a web-sig validation corpus from the RICH
# onyphe sample files (`*_banners_samples.jsonl`, which carry `cpe`).
# Writes NOTHING to patterns/data. No network. Keeps ALL web rows
# (user directive: do NOT drop rows lacking a web-sig cpe match);
# splits into 3 recette-format corpora by bucket so recette-banners
# gives a clean per-bucket web-sig KPI:
#
#   validate     : a cpe:/a: product == a web-sig signature
#                  -> behavioral validation (should our sig fire?)
#   coverage_gap : cpe:/a: is a web-app but NO web-sig exists
#                  -> authoring backlog (expected MISS)
#   unlabeled    : no usable cpe:/a:  -> web-sig may still fire
#                  (discovery / FP surface)
#
# Dedup across the (stat-identical) rich files by sha256(banner).
#
# Usage: python3 a139_build_corpus.py [--sample N] [--outdir DIR]

import argparse
import collections
import glob
import hashlib
import json
from pathlib import Path

TEMP = Path("/opt/lia-sec/dev/_alire/temp")
WS_DIR = Path("/opt/lia-sec/liaprobe/patterns/web-signatures")
WEB_PORTS = {80, 443, 8080, 8443, 8000, 8888}


def websig_vocab() -> set:
    v = set()
    for p in WS_DIR.glob("*.json"):
        try:
            r = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for k in ("taxonomy_name", "product", "id"):
            s = r.get(k)
            if isinstance(s, str) and s.strip():
                v.add(s.strip().lower().replace(" ", "_").replace("-", "_"))
    return v


def cpe_app_products(cpes) -> list:
    """Return product tokens of every cpe:/a: entry.
    cpe:/a:vendor:product:version -> split(':') index 3 = product."""
    if isinstance(cpes, str):
        cpes = [cpes]
    out = []
    for c in cpes or []:
        if isinstance(c, str) and c.startswith("cpe:/a:"):
            parts = c.split(":")
            if len(parts) > 3 and parts[3].strip():
                out.append(parts[3].strip().lower())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0,
                    help="limit input lines per file (0=all)")
    ap.add_argument("--outdir", default=str(TEMP))
    a = ap.parse_args()

    ws = websig_vocab()

    def matches_ws(prod: str) -> bool:
        pn = prod.replace("-", "_")
        if pn in ws:
            return True
        return any(pn in w or w in pn for w in ws if len(pn) > 3)

    outdir = Path(a.outdir)
    fh = {b: open(outdir / f"A139_{b}.jsonl", "w", encoding="utf-8")
          for b in ("validate", "coverage_gap", "unlabeled")}
    counts = collections.Counter()
    seen = set()
    files = sorted(glob.glob(str(TEMP / "*banners_samples*.jsonl")))

    for f in files:
        n = 0
        for ln in open(f, encoding="utf-8", errors="replace"):
            n += 1
            if a.sample and n > a.sample:
                break
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            port = d.get("port")
            try:
                port = int(port)
            except (TypeError, ValueError):
                continue
            if port not in WEB_PORTS:
                continue
            banner = str(d.get("data") or d.get("banner") or "")
            if not banner:
                continue
            h = hashlib.sha256(banner.encode("utf-8", "replace")).hexdigest()
            if h in seen:
                counts["dup_skipped"] += 1
                continue
            seen.add(h)

            apps = cpe_app_products(d.get("cpe"))
            ws_hit = next((p for p in apps if matches_ws(p)), None)
            if ws_hit:
                bucket, gt = "validate", ws_hit
            elif apps:
                bucket, gt = "coverage_gap", apps[0]
            else:
                bucket = "unlabeled"
                gt = (d.get("product") or "").strip().lower()
            counts[bucket] += 1

            rec = {
                "banner": banner,
                "port": port,
                "protocol": d.get("protocol") or "http",
                "state": "open",
                "ground_truth": {"product": gt or "unknown"},
            }
            fh[bucket].write(json.dumps(rec, ensure_ascii=False) + "\n")

    for x in fh.values():
        x.close()
    manifest = {
        "schema": "lia-a139-corpus-v1",
        "note": "READ-ONLY web-sig validation corpus from rich onyphe "
                "cpe samples. KEEP-ALL web rows (no cpe-match drop). "
                "ground_truth.product = cpe:/a: product (validate/"
                "coverage_gap) or onyphe product (unlabeled).",
        "source_files": [Path(x).name for x in files],
        "web_ports": sorted(WEB_PORTS),
        "counts": dict(counts),
        "outputs": {b: f"A139_{b}.jsonl" for b in
                    ("validate", "coverage_gap", "unlabeled")},
    }
    (Path(a.outdir) / "A139_CORPUS_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    for k, v in counts.most_common():
        print(f"  {v:7d} {k}")
    print("manifest:", Path(a.outdir) / "A139_CORPUS_MANIFEST.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
