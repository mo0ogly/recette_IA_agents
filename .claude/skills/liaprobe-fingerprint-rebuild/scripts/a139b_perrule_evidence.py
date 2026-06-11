#!/usr/bin/env python3
# A139b -- READ-ONLY. Resolve the A139 confound: did the web-sig rule
# whose product == a row's cpe ground-truth FIRE (Confidence>0) on its
# target rows, independent of which pattern won the verdict?
# Method: per top-K product in A139_validate, subset rows, run
# recette-banners -trace-pattern <id> on the subset, count fires.
# No mutation, no network.
import json, collections, glob, subprocess, tempfile, os, sys
from pathlib import Path

LIA = Path("/opt/lia-sec/liaprobe"); REC = LIA / "bin/recette-onyphe"
VAL = Path("/opt/lia-sec/dev/_alire/temp/A139_validate.jsonl")
WS = LIA / "patterns/web-signatures"
TOPK = int(sys.argv[1]) if len(sys.argv) > 1 else 10

def norm(s): return s.strip().lower().replace(" ", "_").replace("-", "_")

# product -> websig pattern id (first json whose id/taxonomy/product slug == product)
prod2id = {}
for p in WS.glob("*.json"):
    try: r = json.loads(p.read_text())
    except Exception: continue
    cand = {norm(str(r.get(k))) for k in ("id","taxonomy_name","product") if r.get(k)}
    pid = r.get("id") or p.stem
    for c in cand:
        prod2id.setdefault(c, pid)

rows_by = collections.defaultdict(list)
for ln in open(VAL, encoding="utf-8", errors="replace"):
    try: d = json.loads(ln)
    except Exception: continue
    rows_by[norm(d["ground_truth"]["product"])].append(ln)

top = sorted(rows_by.items(), key=lambda x: -len(x[1]))[:TOPK]
print(f"{'product':22s} {'rows':>5s} {'wsid':24s} {'fired':>5s} {'rate':>6s}")
agg_rows = agg_fired = 0
for prod, lines in top:
    pid = prod2id.get(prod)
    if not pid:
        print(f"{prod:22s} {len(lines):5d} {'(no web-sig id)':24s} {'-':>5s} {'-':>6s}")
        continue
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
            dir="/opt/lia-sec/dev/_alire/temp") as tf:
        tf.writelines(lines); sub = tf.name
    tro = sub + ".trace"
    subprocess.run([str(REC), "-f", sub, "-src", "all", "-out", "json",
                    "-trace-pattern", pid, "-trace-out", tro,
                    "-trace-verdict", "ALL"], cwd=str(LIA),
                   capture_output=True, timeout=600)
    fired = 0
    if os.path.exists(tro):
        try:
            tr = json.load(open(tro))
            for e in tr:
                fr = e.get("target_pattern_result")
                if fr and fr.get("Confidence", 0) > 0:
                    fired += 1
        except Exception:
            pass
    n = len(lines); rate = 100.0*fired/n if n else 0
    agg_rows += n; agg_fired += fired
    print(f"{prod:22s} {n:5d} {pid[:24]:24s} {fired:5d} {rate:5.1f}%")
    os.unlink(sub); 
    if os.path.exists(tro): os.unlink(tro)
ar = 100.0*agg_fired/agg_rows if agg_rows else 0
print(f"\nAGG top{TOPK}: {agg_fired}/{agg_rows} = {ar:.1f}% target-rule fire-rate")
print("interpretation: >>5% => A139 metric was confounded (web-sig OK, "
      "verdict-product granularity). ~5% => web-sig genuinely under-detect.")
