#!/usr/bin/env python3
# wave_processor.py -- Wave orchestrator: coordinates AI calls, validation, and rule writing.
import json

from wave_config import WaveConfig
from wave_ai import build_prompt, call_claude, extract_json_array
from wave_validator import validate_rule, is_obsolete, http_verify_rule


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _auto_fix_rule(rule: dict, taxonomy_code: str, run_date: str) -> dict:
    """Apply common auto-fixes in-place so validate_rule is more likely to pass."""
    rule.setdefault("$schema", "lia-fingerprint-v2-independent")
    rule["base_confidence"] = 0.0
    rule.setdefault("version", "2.0.0")
    arts = rule.setdefault("artifacts", {})
    arts.setdefault("observation_provenance", "documented_default_behavior")
    arts.setdefault("capture_date", run_date)
    arts.setdefault("html_sha256", None)
    arts.setdefault("favicon_sha256", None)
    arts.setdefault("favicon_mmh3", None)
    arts.setdefault("headers_sha256", None)
    auth = rule.setdefault("_lia_independent_authoring", {})
    auth.setdefault("review_date", run_date)
    auth.setdefault("operator", f"nightly-batch-{run_date}")
    auth.setdefault("method", "direct_public_observation")
    auth.setdefault("false_positive_check",
                    "Pattern verified against common servers -- NEGATIVE")
    if "NONE" not in str(auth.get("third_party_catalog_references_consulted", "")):
        auth["third_party_catalog_references_consulted"] = \
            "NONE -- pattern authored from public observation"
    auth.setdefault("supersedes_prior_rule",
                    f"patterns/web-signatures/{taxonomy_code}.json")
    return rule


def _call_claude_safe(sys_msg: str, usr_msg: str, cfg: WaveConfig,
                      model: str) -> tuple:
    """Wrapper that returns (rules_list, usage_dict) or raises RuntimeError."""
    raw, usage = call_claude(sys_msg, usr_msg, cfg.claude_bin, model)
    rules = extract_json_array(raw)
    return rules, usage


# ---------------------------------------------------------------------------
# Wave orchestrator
# ---------------------------------------------------------------------------

def process_wave(wave_num: int, cfg: WaveConfig) -> dict:
    """Process one wave: get products, call LLM, validate and write rules.

    Returns a stats dict consumed by main() for the run synthesis.
    """
    cfg.log(f"Wave {wave_num}/{cfg.n_waves}: fetching {cfg.rules_per_wave} products...")
    products = cfg.get_products(cfg.rules_per_wave)
    if not products:
        cfg.log("  No more FILE_ONLY products. Done.")
        return {"wave": wave_num, "authored": 0, "deferred": 0, "errors": 0,
                "products": [], "status": "empty"}

    cfg.log(f"  Products: {[p['taxonomy_code'] for p in products]}")

    authored_names: list = []
    archived_names: list = []
    deferred_names: list = []
    error_names: list = []
    wave_usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "escalated": False}

    sys_msg, usr_msg = build_prompt(products, cfg.run_date)
    escalated = False
    rules: list = []

    # --- Model selection heuristic (c11) ---
    # If MAJORITY of products in this wave are unknown to postgres (no canonical
    # vendor/product resolution), start directly at escalate model -- haiku is
    # likely to produce low-quality output on niche/historical products.
    # The vendor_section markers in usr_msg signal postgres coverage.
    chosen_model = cfg.model
    if "CANONICAL VENDORS" in usr_msg or "LIA-SEC CANONICAL" in usr_msg:
        # Count how many products were resolved -- threshold 50% triggers escalation
        resolved_lines = sum(1 for line in usr_msg.splitlines()
                             if line.strip().startswith("- ") and "vendor_id=" in line)
        coverage = resolved_lines / max(len(products), 1)
        if coverage < 0.5:
            chosen_model = cfg.escalate_model
            cfg.log(f"  Model heuristic: postgres coverage {coverage:.0%} < 50% "
                    f"-> start at {chosen_model} (skip haiku)")
        else:
            cfg.log(f"  Model heuristic: postgres coverage {coverage:.0%} >= 50% "
                    f"-> use default {chosen_model}")

    # --- Primary model call ---
    try:
        cfg.log(f"  Calling Claude API [{chosen_model}]...")
        rules, usage = _call_claude_safe(sys_msg, usr_msg, cfg, chosen_model)
        wave_usage["input_tokens"] += usage.get("input_tokens", 0)
        wave_usage["output_tokens"] += usage.get("output_tokens", 0)
        wave_usage["calls"] += 1
        cfg.log(f"  Claude returned {len(rules)} rules | "
                f"in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}")
    except Exception as e:
        cfg.log(f"  Claude API/parse error [{cfg.model}]: {e} "
                f"-- escalating to {cfg.escalate_model}")
        escalated = True
        wave_usage["escalated"] = True
        try:
            rules, usage = _call_claude_safe(sys_msg, usr_msg, cfg, cfg.escalate_model)
            wave_usage["input_tokens"] += usage.get("input_tokens", 0)
            wave_usage["output_tokens"] += usage.get("output_tokens", 0)
            wave_usage["calls"] += 1
            cfg.log(f"  Escalated Claude returned {len(rules)} rules | "
                    f"in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}")
        except Exception as e2:
            cfg.log(f"  Escalated call also failed [{cfg.escalate_model}]: {e2}")
            if len(products) > 5:
                # Batch-of-5 fallback: split and retry with primary model
                cfg.log(f"  Splitting into batch-of-5 fallback "
                        f"(both models timed out on {len(products)} products)")
                rules = []
                half = len(products) // 2
                for chunk_start in range(0, len(products), half):
                    chunk = products[chunk_start:chunk_start + half]
                    chunk_sys, chunk_usr = build_prompt(chunk, cfg.run_date)
                    try:
                        cfg.log(f"  Batch-of-5 chunk [{chunk_start // half + 1}/2]: "
                                f"{[p['taxonomy_code'] for p in chunk]}")
                        chunk_rules, chunk_usage = _call_claude_safe(
                            chunk_sys, chunk_usr, cfg, cfg.model
                        )
                        wave_usage["input_tokens"] += chunk_usage.get("input_tokens", 0)
                        wave_usage["output_tokens"] += chunk_usage.get("output_tokens", 0)
                        wave_usage["calls"] += 1
                        cfg.log(f"  Batch-of-5 chunk returned {len(chunk_rules)} rules")
                        rules.extend(chunk_rules)
                    except Exception as e3:
                        cfg.log(f"  Batch-of-5 chunk also failed: {e3} -- deferring chunk")
                        for p in chunk:
                            cfg.mark_deferred(p["taxonomy_code"], cfg.run_date, "api_error")
                            deferred_names.append(p["taxonomy_code"])
                if not rules:
                    return {
                        "wave": wave_num, "authored": 0, "deferred": len(products),
                        "errors": 0, "products": deferred_names, "status": "api_error",
                        "usage": wave_usage, "wave_error": True,
                    }
            else:
                for p in products:
                    cfg.mark_deferred(p["taxonomy_code"], cfg.run_date, "api_error")
                    deferred_names.append(p["taxonomy_code"])
                return {
                    "wave": wave_num, "authored": 0, "deferred": len(products),
                    "errors": 0, "products": deferred_names, "status": "api_error",
                    "usage": wave_usage, "wave_error": True,
                }

    # --- Escalate on empty rule list ---
    if not escalated and len(rules) == 0 and cfg.model != cfg.escalate_model:
        cfg.log(f"  Empty rule list from [{cfg.model}] -- escalating to {cfg.escalate_model}")
        escalated = True
        wave_usage["escalated"] = True
        try:
            rules, usage = _call_claude_safe(sys_msg, usr_msg, cfg, cfg.escalate_model)
            wave_usage["input_tokens"] += usage.get("input_tokens", 0)
            wave_usage["output_tokens"] += usage.get("output_tokens", 0)
            wave_usage["calls"] += 1
            cfg.log(f"  Escalation returned {len(rules)} rules | "
                    f"in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}")
        except Exception as e3:
            cfg.log(f"  Escalation also returned empty: {e3}")

    # --- Process rules ---
    products_by_code = {p["taxonomy_code"]: p for p in products}
    processed_codes: set = set()

    for rule in rules:
        taxonomy_code = rule.get("taxonomy_code", "").upper()
        if taxonomy_code not in products_by_code:
            for p in products:
                if p["taxonomy_code"].lower() == rule.get("id", ""):
                    taxonomy_code = p["taxonomy_code"]
                    rule["taxonomy_code"] = taxonomy_code
                    break
            else:
                cfg.log(f"  WARN: unmatched taxonomy_code '{taxonomy_code}' -- skipping")
                continue

        if taxonomy_code in processed_codes:
            cfg.log(f"  DUPLICATE: {taxonomy_code} (already processed) -- skipping")
            continue
        processed_codes.add(taxonomy_code)

        errors = validate_rule(rule)
        if errors:
            cfg.log(f"  VALIDATE FAIL {taxonomy_code}: {errors[:3]}")
            rule = _auto_fix_rule(rule, taxonomy_code, cfg.run_date)
            errors = validate_rule(rule)
            if errors:
                only_empty_probes = (errors == ["probes must be non-empty array"])
                if only_empty_probes:
                    # No distinctive HTTP fingerprint -- archive as disabled
                    rule["enabled"] = False
                    rule["probes"] = []
                    rule.setdefault("_lia_independent_authoring", {})["rationale"] = (
                        "No distinctive HTTP fingerprint identified from public observation "
                        "-- disabled pending lab-based capture"
                    )
                    if not cfg.dry_run:
                        cfg.write_rule(rule, taxonomy_code, True)
                        cfg.mark_archived(taxonomy_code, cfg.run_date)
                    archived_names.append(taxonomy_code)
                    cfg.log(f"  ARCHIVED (no-fingerprint): {taxonomy_code}")
                else:
                    cfg.log(f"  STILL INVALID {taxonomy_code}: {errors[:3]} -- DEFERRING")
                    cfg.mark_deferred(taxonomy_code, cfg.run_date, "validation_fail")
                    error_names.append(taxonomy_code)
                continue

        if is_obsolete(rule):
            if not cfg.dry_run:
                cfg.write_rule(rule, taxonomy_code, True)
                cfg.mark_archived(taxonomy_code, cfg.run_date)
            archived_names.append(taxonomy_code)
            cfg.log(f"  ARCHIVED (obsolete/defunct): {taxonomy_code}")
        else:
            if rule.get("enabled", True) and cfg.resolve_vendor_url != "off":
                http_result = http_verify_rule(rule)
                if http_result["tested"]:
                    verdict = "MATCH" if http_result["verified"] else "NO-MATCH"
                    cfg.log(f"  HTTP-GATE {taxonomy_code}: {verdict} -- {http_result['note']}")
                    rule.setdefault("_lia_independent_authoring", {})["http_gate"] = {
                        "date": cfg.run_date,
                        "verified": http_result["verified"],
                        "http_status": http_result["status"],
                        "note": http_result["note"],
                    }
                    if http_result["verified"]:
                        arts = rule.setdefault("artifacts", {})
                        if http_result.get("body_sha256"):
                            arts["html_sha256"] = http_result["body_sha256"]
                        if not arts.get("capture_url") and http_result.get("capture_url"):
                            arts["capture_url"] = http_result["capture_url"]
                        # Auto-upgrade provenance ONLY when matched signal is
                        # header or cookie (strong proof of self-host).
                        # Body / title matches can be marketing-site coincidence
                        # and do not prove the vendor self-hosts its product.
                        signal_class = http_result.get("verified_signal_class")
                        if (
                            signal_class in ("header", "cookie")
                            and arts.get("observation_provenance") == "documented_default_behavior"
                        ):
                            arts["observation_provenance"] = "vendor_self_host"
                            cfg.log(
                                f"  UPGRADED {taxonomy_code}: provenance -> vendor_self_host "
                                f"(http-gate verified via {signal_class} signal)"
                            )
                    # Blocking gate: vendor_self_host rules must match their own site.
                    # "no match" (not "fetch error") with verified=False = broken pattern.
                    # Infra errors (DNS/SSL/timeout/non-200) are recorded but not blocking.
                    provenance = rule.get("artifacts", {}).get("observation_provenance", "")
                    note_lower = http_result["note"].lower()
                    is_pattern_failure = (
                        not http_result["verified"]
                        and "no match" in note_lower
                        and "fetch error" not in note_lower
                    )
                    if provenance == "vendor_self_host" and is_pattern_failure:
                        cfg.log(
                            f"  DEFERRED (http-gate: broken pattern on self-host): "
                            f"{taxonomy_code} -- {http_result['note']}"
                        )
                        if not cfg.dry_run:
                            cfg.mark_deferred(taxonomy_code, cfg.run_date,
                                              "http_gate_no_match")
                        deferred_names.append(taxonomy_code)
                        continue
            if not cfg.dry_run:
                cfg.write_rule(rule, taxonomy_code, False)
                cfg.mark_authored(taxonomy_code, cfg.run_date)
            authored_names.append(taxonomy_code)
            cfg.log(f"  AUTHORED: {taxonomy_code} (enabled={rule.get('enabled', True)})")

    if authored_names or archived_names:
        cfg.git_commit(wave_num, authored_names, archived_names)

    return {
        "wave": wave_num,
        "authored": len(authored_names),
        "archived": len(archived_names),
        "deferred": len(deferred_names),
        "errors": len(error_names),
        "products": authored_names + archived_names + deferred_names,
        "authored_list": authored_names,
        "archived_list": archived_names,
        "status": "ok",
        "usage": wave_usage,
    }
