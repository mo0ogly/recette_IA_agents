#!/usr/bin/env python3
# promoter_apply.py
#
# A135b-EXEC apply tool. Executes the staged data/ -> patterns/ promoter
# per SPEC_PROMOTER_A135b_2026-05-15.md (corrected: liaprobe-only commit
# /revert, tier_h_gateable scope, real Go-RE2 V3). One wave per CLI call:
#
#   --origin                 capture the immutable ORIGIN baseline (once)
#   --wave N --size 50       dry-run + apply wave N on tier_h_gateable
#   --apply                  actually mutate+gate+commit (default: dry-run)
#
# Gates per wave (a wave passes only if ALL hold):
#   V1..V5 per file (schema / field-contract / real-RE2 / no-attribution
#          / enabled) -- any fail -> git checkout that file, exclude.
#   PRIMARY  per promoted rule: onyphe match-rate < 5% (FP ceiling).
#   SECONDARY cumulative CORRECT >= ORIGIN.CORRECT AND WRONG <= ORIGIN.WRONG.
#   MIN-SIGNAL >= 1 promoted rule with >= 1 onyphe match (no zero-recall wave).
# FAIL -> git checkout the whole wave, halt, surface (liaprobe-only).

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE = Path("/opt/lia-sec/liaprobe")
PATTERNS = LIAPROBE / "patterns/web-signatures"
DATA = LIAPROBE / "data/fingerprints/web-signatures"
SANITIZE = LIAPROBE / "scripts/sanitize_attributions.py"
RE2CHECK = LIAPROBE / "scripts/re2check.go"
RECETTE = LIAPROBE / "bin/recette-onyphe"
ONYPHE = Path("/opt/lia-sec/dev/_alire/temp/onyphe_recette_16641.jsonl")
TRACK = Path("/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild")
MANIFEST = TRACK / "PROMOTER_RUN_MANIFEST.json"
FP_CEILING = 0.05

_s = importlib.util.spec_from_file_location(
    "ps", Path(__file__).parent / "promoter_select.py")
ps = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ps)

ATTR_TOKENS = ("wappalyzer", "recog", "nuclei", "projectdiscovery",
               "onyphe", "rapid7", "shodan", "censys", "fofa",
               "builtwith", "netcraft", "fingerprinthub", "fingerprintx",
               "nmap", "masscan", "zmap")


def sh(cmd, cwd=LIAPROBE, timeout=900):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                          text=True, timeout=timeout)


def git_hash(path: Path) -> str:
    r = sh(["git", "hash-object", str(path)])
    return r.stdout.strip() if r.returncode == 0 else ""


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"schema": "lia-promoter-run-v1",
            "spec": "SPEC_PROMOTER_A135b_2026-05-15.md",
            "origin": None, "waves": [], "settled": {}}


def save_manifest(m: dict):
    m["updated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n")


def run_recette() -> tuple[dict, dict]:
    """Full recette-onyphe -src all. Returns ({CORRECT,WRONG,MISS,total},
    {pid_lower: match_count})."""
    r = sh([str(RECETTE), "-f", str(ONYPHE), "-src", "all", "-out", "json"],
           timeout=900)
    if r.returncode != 0:
        print(f"FATAL recette-onyphe rc={r.returncode}\n{r.stderr[:500]}",
              file=sys.stderr)
        sys.exit(2)
    verdicts = json.loads(r.stdout)
    counts = {"CORRECT": 0, "WRONG": 0, "MISS": 0, "total": len(verdicts)}
    pid_hits: dict = {}
    for v in verdicts:
        vd = v.get("Verdict")
        if vd in counts:
            counts[vd] += 1
        pid = (v.get("PatternID") or "").lower()
        if pid:
            pid_hits[pid] = pid_hits.get(pid, 0) + 1
    return counts, pid_hits


def candidate_ids(rule: dict, fn: str) -> set:
    ids = set()
    for k in ("id", "taxonomy_code"):
        v = rule.get(k)
        if isinstance(v, str) and v.strip():
            ids.add(v.strip().lower())
    ids.add(Path(fn).stem.lower())
    return ids


def select_gateable(settled: dict) -> list:
    """Re-evaluate selection at HEAD (spec §3), return tier_h_gateable
    filenames not yet settled, deterministically ordered."""
    pat = {p.name for p in PATTERNS.glob("*.json")}
    dat = {p.name for p in DATA.glob("*.json")}
    out = []
    for fn in sorted(pat & dat):
        if fn in settled:
            continue
        P, pe = ps.load(PATTERNS / fn)
        D, de = ps.load(DATA / fn)
        if pe or de or not isinstance(P, dict) or not isinstance(D, dict):
            continue
        if not ps.patterns_broken(P):
            continue
        ok, _ = ps.data_ok(D)
        if not ok:
            continue
        d_eff = ps.effective_targets(D)
        if ps.effective_targets(P) - d_eff:
            continue
        if not (d_eff <= ps.BANNER_EVALUABLE):
            continue
        be = [m for m in ps.effective_matchers(D)
              if m.get("target") in ps.BANNER_EVALUABLE]
        if not any(m.get("match_type") in ps.CONTENT_MATCH for m in be):
            continue  # tier_h_exists / vacuous -> not in scope
        out.append(fn)
    return out


def validate(fn: str) -> tuple[bool, str]:
    """V1..V5 on the post-sanitize patterns/{fn}."""
    rule, err = ps.load(PATTERNS / fn)
    if err or not isinstance(rule, dict):
        return False, f"V1 parse: {err}"
    if rule.get("$schema") not in ps.SCHEMA_ALLOWLIST:
        return False, f"V1 schema {rule.get('$schema')!r}"
    if rule.get("enabled") is not True:
        return False, "V5 enabled!=true"
    ms = ps.all_matchers(rule)
    for i, m in enumerate(ms):
        if m.get("target") in ps.FIELD_REQUIRED and \
                not (m.get("field") or "").strip():
            return False, f"V2 matcher[{i}] {m.get('target')} no field"
    # V3 real Go RE2
    regexes = [m.get("value", "") for m in ms
               if m.get("match_type") in ("regex",) and m.get("value")]
    if regexes:
        r = subprocess.run(["go", "run", str(RE2CHECK)], cwd=str(LIAPROBE),
                            input="\n".join(regexes) + "\n",
                            capture_output=True, text=True, timeout=120)
        if "\tBAD\t" in ("\t" + r.stdout) or "\nBAD\t" in r.stdout \
                or r.stdout.startswith("BAD\t"):
            bad = [ln for ln in r.stdout.splitlines()
                   if ln.startswith("BAD\t")]
            return False, f"V3 RE2: {bad[0][:80] if bad else '?'}"
    # V4 no attribution survives
    blob = json.dumps(rule, ensure_ascii=False).lower()
    for tok in ATTR_TOKENS:
        if tok in blob:
            return False, f"V4 attribution {tok!r} survived"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", action="store_true")
    ap.add_argument("--wave", type=int, default=0)
    ap.add_argument("--size", type=int, default=50)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    m = load_manifest()

    if a.origin:
        if m["origin"]:
            print(f"ORIGIN already captured: {m['origin']}")
            return 0
        c, _ = run_recette()
        m["origin"] = c
        save_manifest(m)
        print(f"ORIGIN captured: {c}")
        return 0

    if not m["origin"]:
        print("FATAL: capture --origin first", file=sys.stderr)
        return 2

    pool = select_gateable(m["settled"])
    print(f"tier_h_gateable unsettled at HEAD: {len(pool)}")
    wave_fns = pool[:a.size]
    if not wave_fns:
        print("nothing left to promote -- DONE")
        return 0
    print(f"--- WAVE {a.wave} dry-run ({len(wave_fns)} files) ---")
    for fn in wave_fns:
        print(f"  {fn}")
    if not a.apply:
        print("\n(dry-run; pass --apply to mutate+gate+commit)")
        return 0

    # APPLY
    applied, excluded = [], []
    for fn in wave_fns:
        sb = git_hash(PATTERNS / fn)
        shutil.copyfile(DATA / fn, PATTERNS / fn)
        subprocess.run(["python3", str(SANITIZE), "--apply",
                        str(PATTERNS / fn)], capture_output=True)
        ok, why = validate(fn)
        if not ok:
            sh(["git", "checkout", "--", f"patterns/web-signatures/{fn}"])
            excluded.append({"fn": fn, "reason": why})
            continue
        applied.append({"fn": fn, "sha_before": sb,
                        "sha_after": git_hash(PATTERNS / fn)})
    print(f"applied={len(applied)} excluded={len(excluded)}")
    for e in excluded:
        print(f"  excl {e['fn']}: {e['reason']}")

    if not applied:
        print("WAVE empty after validation -- nothing committed")
        m["waves"].append({"wave": a.wave, "result": "empty",
                           "excluded": excluded})
        save_manifest(m)
        return 0

    # gates
    post, pid_hits = run_recette()
    origin = m["origin"]
    sec_ok = (post["CORRECT"] >= origin["CORRECT"] and
              post["WRONG"] <= origin["WRONG"])
    fp_rejected, signal = [], 0
    for e in list(applied):
        rule, _ = ps.load(PATTERNS / e["fn"])
        cids = candidate_ids(rule or {}, e["fn"])
        hits = sum(pid_hits.get(c, 0) for c in cids)
        rate = hits / max(post["total"], 1)
        e["onyphe_hits"], e["match_rate"] = hits, round(rate, 5)
        if rate >= FP_CEILING:
            fp_rejected.append(e)
            applied.remove(e)
        elif hits >= 1:
            signal += 1

    halt = None
    if fp_rejected:
        for e in fp_rejected:
            sh(["git", "checkout", "--",
                f"patterns/web-signatures/{e['fn']}"])
        # re-run after FP reverts so SECONDARY reflects committed state
        post, _ = run_recette()
        sec_ok = (post["CORRECT"] >= origin["CORRECT"] and
                  post["WRONG"] <= origin["WRONG"])
    if not sec_ok:
        halt = (f"SECONDARY fail: CORRECT {post['CORRECT']}<"
                f"{origin['CORRECT']} or WRONG {post['WRONG']}>"
                f"{origin['WRONG']}")
    elif signal == 0:
        halt = "MIN-SIGNAL fail: 0 promoted rule has an onyphe match"

    if halt:
        for e in applied:
            sh(["git", "checkout", "--",
                f"patterns/web-signatures/{e['fn']}"])
        print(f"WAVE {a.wave} HALT -- {halt} (whole wave reverted)")
        m["waves"].append({"wave": a.wave, "result": "halt",
                           "reason": halt, "post": post,
                           "fp_rejected": [x["fn"] for x in fp_rejected],
                           "excluded": excluded})
        save_manifest(m)
        return 3

    # PASS -> liaprobe-only commit (CRITICAL-e)
    for e in applied:
        sh(["git", "add", f"patterns/web-signatures/{e['fn']}"])
    staged = sh(["git", "diff", "--cached", "--name-only"]).stdout.strip()
    msg = (f"feat(web-sig): A135b promoter wave {a.wave} -- "
           f"{len(applied)} tier_h_gateable rules recovered from data/\n\n"
           f"Per SPEC_PROMOTER_A135b_2026-05-15.md. V1-V5 + PRIMARY "
           f"(<5% onyphe FP) + SECONDARY (CORRECT>={origin['CORRECT']} "
           f"WRONG<={origin['WRONG']}, got C={post['CORRECT']} "
           f"W={post['WRONG']}) + min-signal({signal}) passed. "
           f"fp_rejected={len(fp_rejected)} excluded={len(excluded)}.")
    cm = sh(["git", "commit", "-q", "-m", msg])
    head = sh(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    for e in applied:
        m["settled"][e["fn"]] = {"wave": a.wave, "status": "promoted",
                                 "commit": head, **e}
    for e in excluded:
        m["settled"][e["fn"]] = {"wave": a.wave, "status": "excluded",
                                 "reason": e["reason"]}
    for e in fp_rejected:
        m["settled"][e["fn"]] = {"wave": a.wave, "status": "fp_rejected",
                                 "match_rate": e["match_rate"]}
    m["waves"].append({"wave": a.wave, "result": "pass", "commit": head,
                       "promoted": len(applied), "fp_rejected": len(fp_rejected),
                       "excluded": len(excluded), "signal": signal,
                       "post": post})
    save_manifest(m)
    print(f"WAVE {a.wave} PASS commit={head} promoted={len(applied)} "
          f"staged_files={len(staged.splitlines())} "
          f"C={post['CORRECT']} W={post['WRONG']} signal={signal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
