#!/usr/bin/env python3
# trace_verdict.py
#
# Diagnostic tool : for a given banner (identified by ip+port or row index
# in Onyphe merged file), runs the engine on the full corpus + extracts
# the SINGLE verdict for that banner, then Python-side replays each
# matcher of the winning rule to identify which one fired.
#
# Workaround for missing engine tracer flag. Helps c10+ investigate
# mystery FPs where engine PatternID seems to contradict rule matchers.
#
# Usage:
#   python3 trace_verdict.py --ip 1.2.3.4 --port 443
#   python3 trace_verdict.py --row 1234       # row index in merged jsonl
#   python3 trace_verdict.py --pid gfi_kerio_connect --limit 3  # 3 FPs of this rule

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"
RECETTE_BIN = LIAPROBE_DIR / "bin/recette-onyphe"
DEV_DIR = Path("/opt/lia-sec/dev")
DEFAULT_ONYPHE = DEV_DIR / "_alire/temp/onyphe_merged_unique_2026-05-12.jsonl"


def load_banners() -> list:
    out = []
    with open(DEFAULT_ONYPHE) as f:
        for i, line in enumerate(f):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            d["_row"] = i
            out.append(d)
    return out


def find_rule_by_pid(pid: str) -> dict:
    pid_low = pid.lower()
    for path in PATTERNS_ROOT.rglob("*.json"):
        if "/archive/" in str(path):
            continue
        try:
            r = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if (r.get("id") or "").lower() == pid_low:
            return {"path": str(path.relative_to(LIAPROBE_DIR)), "rule": r}
    return {}


def parse_http_headers(banner: str) -> dict:
    """Best-effort: extract header dict from raw banner."""
    headers = {}
    cookies = {}
    if "\r\n\r\n" in banner:
        head, body = banner.split("\r\n\r\n", 1)
    elif "\n\n" in banner:
        head, body = banner.split("\n\n", 1)
    else:
        head, body = banner, ""
    for line in re.split(r"\r?\n", head)[1:]:
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k_low = k.strip().lower()
        v = v.strip()
        if k_low == "set-cookie":
            # Parse cookie name=value
            if "=" in v:
                name, _, _ = v.partition(";")[0].partition("=")
                cookies[name.strip().lower()] = v
        headers[k_low] = v
    return {"headers": headers, "body": body, "cookies": cookies}


def replay_matcher(matcher: dict, banner: str, parsed: dict) -> dict:
    """Replay a single matcher Python-side. Returns {matched, evidence}."""
    target = matcher.get("target", "")
    field = (matcher.get("field") or "").lower()
    value = matcher.get("value", "")
    mt = matcher.get("match_type", "regex")
    ci = matcher.get("case_insensitive", False)

    # Resolve data to test against target
    data = ""
    if target == "banner":
        data = banner
    elif target == "body":
        data = parsed["body"]
    elif target == "header":
        if not field:
            data = " ".join(parsed["headers"].values())
        else:
            data = parsed["headers"].get(field, "")
    elif target == "cookie":
        data = parsed["cookies"].get(field, "")

    if data == "" and target in ("header", "cookie") and field:
        return {"matched": False, "evidence": f"field '{field}' absent in parsed banner"}

    if mt == "regex":
        flags = re.IGNORECASE if ci else 0
        try:
            m = re.search(value, data, flags)
            if m:
                return {"matched": True, "evidence": f"regex matched: {m.group(0)[:80]!r}"}
        except re.error as e:
            return {"matched": False, "evidence": f"regex error: {e}"}
    elif mt == "contains":
        if value.lower() in data.lower():
            return {"matched": True, "evidence": f"contains '{value}' in data[{len(data)}]"}
    elif mt == "exact":
        if value.lower() == data.lower():
            return {"matched": True, "evidence": "exact match"}
    elif mt == "exists":
        if data:
            return {"matched": True, "evidence": "field present non-empty"}
    return {"matched": False, "evidence": f"no match (mt={mt} on {len(data)} chars)"}


def trace_one(banner_obj: dict, verdicts: list) -> None:
    ip = banner_obj.get("ground_truth", {}).get("ip", "?")
    port = banner_obj.get("port")
    gt = banner_obj.get("ground_truth", {}).get("product", "?")
    banner = banner_obj.get("banner", "")
    parsed = parse_http_headers(banner)

    print(f"\n=== Banner ip={ip} port={port} gt={gt} (banner len {len(banner)}) ===")

    # Find engine verdict for this banner
    matching = [v for v in verdicts
                if v.get("Port") == port
                and v.get("GTProduct") == gt
                and (v.get("Banner") or "")[:30] == banner[:30].replace("\r", ".").replace("\n", ".")]
    if not matching:
        # Try just port+gt
        matching = [v for v in verdicts
                    if v.get("Port") == port and v.get("GTProduct") == gt]
    if matching:
        ev = matching[0]
        print(f"Engine verdict     : {ev.get('Verdict')}")
        print(f"Engine PatternID   : {ev.get('PatternID')}")
        print(f"Engine DetProduct  : {ev.get('DetProduct')}")
        print(f"Engine DetConf     : {ev.get('DetConf')}")
        pid = (ev.get("PatternID") or "").lower()
    else:
        print("(no engine verdict found for this banner)")
        return

    if not pid:
        print("(no PatternID -- engine had no detection)")
        return

    # Load winning rule + replay each matcher
    info = find_rule_by_pid(pid)
    if not info:
        print(f"(rule with id={pid!r} not found on disk)")
        return
    rule = info["rule"]
    print(f"Rule file          : {info['path']}")
    print(f"Rule product       : {rule.get('product')!r}")
    print()
    print("Per-matcher replay (Python-side, may differ from engine slightly):")
    for probe_i, probe in enumerate(rule.get("probes", [])):
        for m_i, m in enumerate(probe.get("matchers", [])):
            res = replay_matcher(m, banner, parsed)
            mark = "MATCH" if res["matched"] else "----"
            print(f"  [{probe_i}/{m_i}] {mark}  target={m.get('target')} "
                  f"field={m.get('field', '')!r} mt={m.get('match_type')} "
                  f"value={(m.get('value') or '')[:50]!r}")
            print(f"        -> {res['evidence'][:120]}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ip", type=str)
    p.add_argument("--port", type=int)
    p.add_argument("--row", type=int, help="0-indexed row in merged Onyphe jsonl")
    p.add_argument("--pid", type=str, help="Trace N FPs of this PatternID")
    p.add_argument("--limit", type=int, default=3)
    args = p.parse_args()

    print(f"[INFO] Loading banners from {DEFAULT_ONYPHE.name}...")
    banners = load_banners()
    print(f"[INFO] {len(banners)} banners loaded")

    print("[INFO] Running engine...")
    proc = subprocess.run(
        [str(RECETTE_BIN), "-f", str(DEFAULT_ONYPHE), "-out", "json", "-src", "all"],
        cwd=str(LIAPROBE_DIR), capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        print(f"[ERROR] engine: {proc.stderr}", file=sys.stderr)
        sys.exit(2)
    verdicts = json.loads(proc.stdout)
    print(f"[INFO] {len(verdicts)} engine verdicts")

    targets = []
    if args.pid:
        fps = [v for v in verdicts
               if (v.get("PatternID") or "").lower() == args.pid.lower()
               and v.get("Verdict") == "WRONG"]
        for v in fps[:args.limit]:
            # find matching banner_obj
            for b in banners:
                if (b.get("port") == v.get("Port")
                        and b.get("ground_truth", {}).get("product") == v.get("GTProduct")):
                    targets.append(b)
                    break
    elif args.row is not None:
        targets = [banners[args.row]] if 0 <= args.row < len(banners) else []
    elif args.ip and args.port:
        for b in banners:
            gt = b.get("ground_truth", {})
            if gt.get("ip") == args.ip and b.get("port") == args.port:
                targets.append(b)
                break

    if not targets:
        print("[ERROR] no banners matched selector", file=sys.stderr)
        sys.exit(3)

    for t in targets:
        trace_one(t, verdicts)


if __name__ == "__main__":
    sys.exit(main())
