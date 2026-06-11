#!/usr/bin/env python3
# onyphe_audit_web.py
#
# Audit liaprobe web-signatures rules against Onyphe HTTP ground-truth
# banners. Measures precision/recall per rule and identifies coverage gaps.
#
# Input  : _alire/temp/onyphe_recette_full_6265.jsonl (3000 HTTP banners)
# Output : _alire/tracking/liaprobe-fingerprint-rebuild/ONYPHE_AUDIT_WEB_<DATE>.json
#
# Classifications per (rule, banner) pair:
#   TP        : rule matched + rule.product == ground_truth.product (normalized)
#   FP        : rule matched + rule.product != ground_truth.product
#   MATCH_*   : audit-only, no ground-truth product comparison possible
# Per-banner system metrics:
#   UNCOVERED : ground_truth.product is not the product of any rule in corpus
#   FN_BANNER : ground_truth.product is in corpus but no matching rule fired
#
# Usage:
#   python3 onyphe_audit_web.py --sample 5
#   python3 onyphe_audit_web.py --apply
#   python3 onyphe_audit_web.py --apply --limit 500  # subset

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_DIR = LIAPROBE_DIR / "patterns/web-signatures"
DEV_DIR = Path("/opt/lia-sec/dev")
ONYPHE_FILE = DEV_DIR / "_alire/temp/onyphe_recette_full_6265.jsonl"
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# HTTP banner parser
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"<title[^>]*>([^<]*)</title>", re.IGNORECASE)


def parse_http_banner(banner: str) -> dict:
    """Parse raw HTTP response banner.

    Returns {status_code, headers, body, cookies, title}.
    Tolerant to malformed input -- best-effort.
    """
    out = {"status_code": 0, "headers": {}, "body": "", "cookies": "", "title": ""}
    if not banner or not isinstance(banner, str):
        return out

    # Decode hex escapes used by Onyphe (\xNN sequences are literal text in jsonl).
    # Onyphe banner text already contains \r\n as actual chars in many cases,
    # but some bytes encoded as "\xNN" literal sequences. Best-effort decode.
    try:
        decoded = banner.encode("latin-1").decode("unicode_escape", errors="replace")
    except Exception:
        decoded = banner

    # Split headers / body on first blank line (\r\n\r\n or \n\n)
    if "\r\n\r\n" in decoded:
        head, body = decoded.split("\r\n\r\n", 1)
    elif "\n\n" in decoded:
        head, body = decoded.split("\n\n", 1)
    else:
        head, body = decoded, ""

    lines = re.split(r"\r?\n", head)
    if not lines:
        return out

    # Status line: "HTTP/1.1 200 OK"
    m = re.match(r"HTTP/\d\.\d\s+(\d+)", lines[0])
    if m:
        out["status_code"] = int(m.group(1))

    cookies_parts = []
    for line in lines[1:]:
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k_low = k.strip().lower()
        v = v.strip()
        if k_low == "set-cookie":
            cookies_parts.append(v)
        # Headers may repeat (e.g. Set-Cookie). Last one wins for generic dict.
        out["headers"][k_low] = v

    out["body"] = body
    out["cookies"] = "; ".join(cookies_parts)

    m = _TITLE_RE.search(body)
    if m:
        out["title"] = m.group(1).strip()

    return out


# ---------------------------------------------------------------------------
# Rule matcher evaluator
# ---------------------------------------------------------------------------

def evaluate_matcher(target: str, field: str, pattern: str, parsed: dict) -> bool:
    """Return True if `pattern` (regex) matches the relevant slice of `parsed`."""
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return False

    if target in ("body", "html"):
        return bool(rx.search(parsed.get("body", "")))
    if target == "title":
        return bool(rx.search(parsed.get("title", "")))
    if target == "cookie":
        return bool(rx.search(parsed.get("cookies", "")))
    if target == "header":
        if field:
            headers = parsed.get("headers", {})
            field_low = field.lower()
            if field_low not in headers:
                # Absent header: never matches (interpretation per rule intent --
                # "field" specifies which header to inspect; absence != empty).
                return False
            return bool(rx.search(headers[field_low]))
        for v in parsed.get("headers", {}).values():
            if rx.search(v):
                return True
        return False
    return False


def evaluate_rule(rule: dict, parsed: dict) -> dict:
    """Evaluate all matchers in a rule against parsed banner.

    Returns {matched: bool, signal_class: header|cookie|body|title|None}.
    Reports the FIRST matching matcher's signal class.
    """
    for probe in rule.get("probes", []) or []:
        for m in probe.get("matchers", []) or []:
            if m.get("match_type") != "regex":
                continue
            pattern = m.get("value", "")
            if not pattern:
                continue
            target = m.get("target", "body")
            field = m.get("field", "")
            if evaluate_matcher(target, field, pattern, parsed):
                # Map target -> signal_class for downstream prioritization
                if target == "header":
                    sc = "header"
                elif target == "cookie":
                    sc = "cookie"
                elif target == "title":
                    sc = "title"
                else:
                    sc = "body"
                return {"matched": True, "signal_class": sc, "pattern": pattern[:60]}
    return {"matched": False, "signal_class": None, "pattern": None}


# ---------------------------------------------------------------------------
# Product normalization + coverage map
# ---------------------------------------------------------------------------

def normalize_product(s: str) -> str:
    """Canonical product key: lowercase + drop non-alphanum."""
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def extract_rule_product(rule: dict, fallback_code: str) -> str:
    """Extract rule product name, tolerant to v1-legacy vs v2-independent schemas."""
    # v2: product field
    p = rule.get("product")
    if isinstance(p, str) and p:
        return p
    # v2: taxonomy_name
    tn = rule.get("taxonomy_name")
    if isinstance(tn, str) and tn:
        return tn
    # v1-legacy: name / id
    for k in ("name", "id", "taxonomy_code"):
        v = rule.get(k)
        if isinstance(v, str) and v:
            return v
    # last resort: filename stem
    return fallback_code


def is_rule_enabled(rule: dict) -> bool:
    """True if rule should participate in audit. Legacy default = True."""
    if "enabled" in rule:
        return bool(rule["enabled"])
    return True


# ---------------------------------------------------------------------------
# Audit loop
# ---------------------------------------------------------------------------

def load_rules() -> list:
    """Load all .json rules (v2 + v1 legacy). Skip archive/."""
    rules = []
    for path in sorted(PATTERNS_DIR.glob("*.json")):
        try:
            rule = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not is_rule_enabled(rule):
            continue
        code = rule.get("taxonomy_code") or path.stem
        product = extract_rule_product(rule, code)
        rules.append({
            "path": path,
            "code": code,
            "product": product,
            "product_norm": normalize_product(product),
            "rule": rule,
        })
    return rules


def load_http_banners(limit: int = 0) -> list:
    """Load HTTP-protocol banners from Onyphe recette file."""
    banners = []
    with open(ONYPHE_FILE) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("protocol") != "http":
                continue
            banners.append(d)
            if limit and len(banners) >= limit:
                break
    return banners


def audit(rules: list, banners: list, sample: bool = False) -> dict:
    """Run the audit. Returns aggregated report dict."""
    # Build coverage map: normalized product -> list of rule codes
    coverage = {}
    for r in rules:
        if r["product_norm"]:
            coverage.setdefault(r["product_norm"], []).append(r["code"])

    per_rule = {r["code"]: {"product": r["product"], "tp": 0, "fp": 0,
                              "tp_evidence": [], "fp_evidence": []}
                for r in rules}
    per_banner = []
    uncovered_products = {}
    fn_count = 0

    for i, banner_obj in enumerate(banners, 1):
        gt_product = banner_obj.get("ground_truth", {}).get("product", "")
        gt_norm = normalize_product(gt_product)
        banner_str = banner_obj.get("banner", "")
        parsed = parse_http_banner(banner_str)

        matched_rules = []  # list of (code, signal_class, verdict)
        banner_ip = banner_obj.get("ground_truth", {}).get("ip", "")
        for r in rules:
            res = evaluate_rule(r["rule"], parsed)
            if not res["matched"]:
                continue
            evidence_item = {
                "ip": banner_ip,
                "gt_product": gt_product,
                "signal_class": res["signal_class"],
                "pattern": res["pattern"],
            }
            if gt_norm and r["product_norm"] == gt_norm:
                verdict = "TP"
                per_rule[r["code"]]["tp"] += 1
                # Cap stored evidence to avoid blowup; first 20 per rule.
                if len(per_rule[r["code"]]["tp_evidence"]) < 20:
                    per_rule[r["code"]]["tp_evidence"].append(evidence_item)
            elif gt_norm:
                verdict = "FP"
                per_rule[r["code"]]["fp"] += 1
                if len(per_rule[r["code"]]["fp_evidence"]) < 5:
                    per_rule[r["code"]]["fp_evidence"].append(evidence_item)
            else:
                verdict = "MATCH_NO_GT"
            matched_rules.append({
                "rule_code": r["code"],
                "signal_class": res["signal_class"],
                "verdict": verdict,
            })

        # Coverage analysis per banner
        banner_classification = "MATCH"
        if gt_norm:
            if gt_norm not in coverage:
                uncovered_products[gt_product] = uncovered_products.get(gt_product, 0) + 1
                banner_classification = "UNCOVERED"
            elif not any(m["verdict"] == "TP" for m in matched_rules):
                # Product is covered but no TP fired on this banner -- broken rule
                fn_count += 1
                banner_classification = "FN_BANNER"
            else:
                banner_classification = "TP"

        if sample or i <= 3:
            per_banner.append({
                "i": i,
                "gt_product": gt_product,
                "status_code": parsed["status_code"],
                "server_header": parsed["headers"].get("server", "")[:80],
                "matched_rules": matched_rules,
                "classification": banner_classification,
            })

    # Per-rule precision (TP / TP+FP)
    for code, m in per_rule.items():
        denom = m["tp"] + m["fp"]
        m["precision"] = round(m["tp"] / denom, 3) if denom else None
        m["total_matches"] = denom

    # Global metrics
    total_banners = len(banners)
    covered = sum(1 for b in per_banner if b.get("classification") == "TP") if sample else None
    summary = {
        "schema": "lia-onyphe-audit-web-v1",
        "run_date": RUN_DATE,
        "total_banners": total_banners,
        "total_rules_audited": len(rules),
        "fn_banner_count": fn_count,
        "uncovered_product_count": len(uncovered_products),
        "uncovered_products_top": dict(sorted(uncovered_products.items(),
                                              key=lambda x: -x[1])[:30]),
    }
    return {
        "summary": summary,
        "per_rule": per_rule,
        "per_banner_sample": per_banner if sample else per_banner[:50],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sample", type=int, default=0,
                   help="Audit only first N banners (no JSON report)")
    p.add_argument("--apply", action="store_true",
                   help="Audit ALL HTTP banners and write JSON report")
    p.add_argument("--limit", type=int, default=0,
                   help="Cap banners count for testing (default 0 = no cap)")
    args = p.parse_args()

    if args.sample <= 0 and not args.apply:
        p.error("Specify --sample N or --apply")

    print(f"[INFO] Loading rules from {PATTERNS_DIR}...")
    rules = load_rules()
    print(f"[INFO] {len(rules)} enabled rules loaded (v2 + v1-legacy)")

    if args.sample > 0:
        banners = load_http_banners(limit=args.sample)
        print(f"[INFO] Sample mode: {len(banners)} HTTP banners")
        report = audit(rules, banners, sample=True)
        print()
        print("PER-BANNER SAMPLE:")
        for b in report["per_banner_sample"]:
            print(f"  [{b['i']}] gt={b['gt_product']:25s} status={b['status_code']} "
                  f"server={b['server_header'][:30]:30s} class={b['classification']}")
            for m in b["matched_rules"][:5]:
                print(f"      -> {m['rule_code']:20s} signal={m['signal_class']} verdict={m['verdict']}")
        print()
        print("SUMMARY:")
        for k, v in report["summary"].items():
            if k != "uncovered_products_top":
                print(f"  {k}: {v}")
        return 0

    banners = load_http_banners(limit=args.limit)
    print(f"[INFO] Mass mode: {len(banners)} HTTP banners")
    report = audit(rules, banners, sample=False)

    out = TRACKING_DIR / f"ONYPHE_AUDIT_WEB_{RUN_DATE}.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Rule evidence report: rules with TP > 0 (proof of real-traffic detection)
    proven_rules = {
        code: {
            "product": m["product"],
            "tp": m["tp"],
            "fp": m["fp"],
            "precision": m["precision"],
            "tp_evidence": m["tp_evidence"],
        }
        for code, m in report["per_rule"].items()
        if m["tp"] > 0
    }
    evidence_path = TRACKING_DIR / f"ONYPHE_RULE_EVIDENCE_{RUN_DATE}.json"
    evidence_doc = {
        "schema": "lia-onyphe-rule-evidence-v1",
        "run_date": RUN_DATE,
        "total_banners_audited": len(banners),
        "rules_with_tp": len(proven_rules),
        "rules_audited": len(rules),
        "rules": proven_rules,
    }
    with open(evidence_path, "w") as f:
        json.dump(evidence_doc, f, indent=2, ensure_ascii=False)
    print(f"\n[EVIDENCE] {len(proven_rules)} rules have >=1 TP match in Onyphe ground-truth")
    print(f"           Evidence report: {evidence_path}")

    print()
    print("SUMMARY:")
    for k, v in report["summary"].items():
        if k == "uncovered_products_top":
            print(f"  uncovered_products_top (count={len(v)}):")
            for p_, c in list(v.items())[:10]:
                print(f"    {p_}: {c}")
        else:
            print(f"  {k}: {v}")

    # Top-30 rules by precision (with min 5 matches)
    significant = {k: v for k, v in report["per_rule"].items() if v["total_matches"] >= 5}
    print(f"\nRULES with >=5 matches: {len(significant)}")
    if significant:
        worst = sorted(significant.items(), key=lambda x: x[1]["precision"] or 0)[:10]
        print("\nWORST PRECISION (>=5 matches):")
        for code, m in worst:
            print(f"  {code:30s} precision={m['precision']} (tp={m['tp']} fp={m['fp']})")

    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
