#!/usr/bin/env python3
"""
run_enrich -- LiaProbe rule enrichment orchestrator.

Modes:
  1. Procedural : --cycles 4,5,7  (run specified cycles in order)
  2. Agentic    : --ooda          (OODA loop until target_score reached)

Targets:
  --rule path/to/rule.json         single rule
  --rules-dir patterns/lia/        all rules in directory

Examples:
  python3 run_enrich.py --rule patterns/lia/JENKINS.json --cycles 4,5,7
  python3 run_enrich.py --rule patterns/lia/JENKINS.json --ooda
  python3 run_enrich.py --rules-dir patterns/lia --ooda --target 60

PostgreSQL credentials via DATABASE_URL or LIA_DB_*/PG* env vars.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import enrich_lib as el  # noqa: E402
from ooda_engine import (  # noqa: E402
    OODAEngine,
    OODAResult,
    compute_transformative_score,
)

LOG = logging.getLogger("run_enrich")


# Cycle handler registry -- lazy-load to avoid hard dep failures

def _load_handlers() -> dict:
    handlers = {}
    try:
        import enrich_cycle_4_cve as c4
        handlers["cycle_4_cve"] = c4.handle
    except Exception as e:
        LOG.warning("cycle_4 unavailable: %s", e)
    try:
        import enrich_cycle_6_compliance as c6
        handlers["cycle_6_compliance"] = c6.handle
    except Exception as e:
        LOG.warning("cycle_6 unavailable: %s", e)
    try:
        import enrich_cycle_5_eol as c5
        handlers["cycle_5_eol"] = c5.handle
    except Exception as e:
        LOG.warning("cycle_5 unavailable: %s", e)
    try:
        import enrich_cycle_7_mitre as c7
        handlers["cycle_7_mitre"] = c7.handle
    except Exception as e:
        LOG.warning("cycle_7 unavailable: %s", e)
    try:
        import enrich_cycle_8_default_creds as c8
        handlers["cycle_8_default_creds"] = c8.handle
    except Exception as e:
        LOG.warning("cycle_8 unavailable: %s", e)
    try:
        import enrich_cycle_9_cert_patterns as c9
        handlers["cycle_9_cert_patterns"] = c9.handle
    except Exception as e:
        LOG.warning("cycle_9 unavailable: %s", e)
    try:
        import enrich_cycle_10_http_behavior as c10
        handlers["cycle_10_behavior"] = c10.handle
    except Exception as e:
        LOG.warning("cycle_10 unavailable: %s", e)
    try:
        import enrich_cycle_11_cluster_tls as c11
        handlers["cycle_11_cluster_tls"] = c11.handle
    except Exception as e:
        LOG.warning("cycle_11 unavailable: %s", e)
    try:
        import enrich_cycle_12_honeypot as c12
        handlers["cycle_12_honeypot"] = c12.handle
    except Exception as e:
        LOG.warning("cycle_12 unavailable: %s", e)
    return handlers


CYCLE_NUMERIC_MAP = {
    "4": "cycle_4_cve",
    "5": "cycle_5_eol",
    "6": "cycle_6_compliance",
    "7": "cycle_7_mitre",
    "8": "cycle_8_default_creds",
    "9": "cycle_9_cert_patterns",
    "10": "cycle_10_behavior",
    "11": "cycle_11_cluster_tls",
    "12": "cycle_12_honeypot",
}

# c21: batch action types -> equivalent cycle id. consume_enrich_queue.py
# emits queued action verbs (NEXT_ENRICH_QUEUE pattern) that don't always
# match skill cycle filenames 1:1. This dispatcher maps them.
# `cpe23_template_fill` is a local mutation (not a cycle): handled inline
# in _apply_batch_inline_actions before cycle dispatch.
BATCH_ACTION_TO_CYCLE = {
    "cve_lookup": "cycle_4_cve",
    "version_compare": "cycle_5_eol",
    "eol_check": "cycle_5_eol",
    "mitre_attack": "cycle_7_mitre",
    "default_creds_check": "cycle_8_default_creds",
    "cert_patterns": "cycle_9_cert_patterns",
    "compliance_mapping": "cycle_6_compliance",
}
BATCH_ACTION_INLINE = {"cpe23_template_fill"}


def _resolve_cycle_id(token: str) -> str | None:
    token = token.strip()
    if token in CYCLE_NUMERIC_MAP:
        return CYCLE_NUMERIC_MAP[token]
    if token.startswith("cycle_"):
        return token
    return None


def _derive_cycles_from_batch(batch_path: Path) -> tuple[list[str], list[dict]]:
    """Parse batch JSON, return (cycle_ids, inline_actions).

    inline_actions = [{rule_file, action, action_params, ...}] for actions
    that don't map to a cycle (cpe23_template_fill).
    Cycle ids deduped + ordered (lowest cycle number first).
    """
    data = json.loads(batch_path.read_text())
    if data.get("schema") != "lia-enrich-batch-v1":
        raise SystemExit(f"batch schema mismatch: {data.get('schema')!r}")
    cycles: set[str] = set()
    inline: list[dict] = []
    for action_type, entries in (data.get("batches") or {}).items():
        if action_type in BATCH_ACTION_TO_CYCLE:
            cycles.add(BATCH_ACTION_TO_CYCLE[action_type])
        elif action_type in BATCH_ACTION_INLINE:
            for e in entries:
                inline.append({**e, "action_type": action_type})
        # else: unknown action, silently skipped (will be flagged in summary)
    # Sort cycles numerically by suffix int when possible
    def _key(c):
        for n, cid in CYCLE_NUMERIC_MAP.items():
            if cid == c:
                return int(n)
        return 99
    return (sorted(cycles, key=_key), inline)


def _apply_inline_action(action: dict, liaprobe_root: Path) -> dict:
    """Inline action handler. Currently only cpe23_template_fill.
    Mutates the rule in place when conditions are met. Returns audit dict.
    """
    rule_file = action.get("rule_file")
    if not rule_file:
        return {"status": "skipped", "reason": "no_rule_file"}
    path = (liaprobe_root / rule_file).resolve()
    if not path.exists():
        return {"status": "skipped", "reason": "rule_file_missing", "path": str(path)}
    try:
        rule = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "error", "reason": f"json_decode: {e}"}

    if action["action_type"] == "cpe23_template_fill":
        params = action.get("action_params") or {}
        current = rule.get("cpe23_template") or ""
        proposed = params.get("proposed") or ""
        if current.strip():
            return {"status": "skipped", "reason": "cpe23_template_already_set",
                    "current": current}
        if not proposed.strip():
            return {"status": "skipped", "reason": "no_proposed_value"}
        rule["cpe23_template"] = proposed
        auth = rule.setdefault("_lia_independent_authoring", {})
        auth.setdefault("inline_action_history", []).append({
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": "cpe23_template_fill",
            "from": current,
            "to": proposed,
            "rationale": params.get("rationale"),
            "marked_by": "run_enrich.py inline action c21",
        })
        path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
        return {"status": "applied", "from": current, "to": proposed}
    return {"status": "unknown_action", "action": action["action_type"]}


def _resolve_liaprobe_root() -> Path:
    env = os.environ.get("LIAPROBE_ROOT")
    if env:
        p = Path(env).resolve()
        if p.exists():
            return p
    return Path("/opt/lia-sec/liaprobe").resolve()


def _build_components(liaprobe_root: Path) -> tuple[el.StateManager, el.EvidenceWriter]:
    state_dir = liaprobe_root / "_alire/tracking/liaprobe-enrich-v2/runtime/enrich_state"
    sm = el.StateManager(state_dir)
    ew = el.EvidenceWriter(
        enrichment_root=liaprobe_root / "data/enrichment",
        fingerprints_root=liaprobe_root / "data/fingerprints",
        patterns_root=liaprobe_root / "patterns",
    )
    return sm, ew


def _go_validate(rule_paths: list[Path], liaprobe_root: Path) -> dict:
    """Run the Go fingerprint validator on the enriched rule files.

    Locates `bin/lia-rule-validate` under the liaprobe root; rebuilds it from
    `cmd/lia-rule-validate/` when absent (binary is gitignored). Returns a
    summary dict {available, built, total, passed, failed, failures[]}.

    This is the same validator the pre-commit hook runs (`-q -allow-disabled`);
    invoking it here surfaces schema breakage BEFORE the commit gate. Opt-in via
    --go-validate so default batch runs stay PG-only and side-effect-free.
    """
    out: dict = {"available": False, "built": False, "total": len(rule_paths),
                 "passed": 0, "failed": 0, "failures": []}
    if not rule_paths:
        return out

    binary = liaprobe_root / "bin" / "lia-rule-validate"
    if not binary.exists():
        go = shutil.which("go")
        src = liaprobe_root / "cmd" / "lia-rule-validate"
        if go and src.is_dir():
            try:
                subprocess.run(
                    [go, "build", "-o", str(binary), "./cmd/lia-rule-validate/"],
                    cwd=str(liaprobe_root), capture_output=True, text=True,
                    timeout=120, check=True,
                )
                out["built"] = True
            except (OSError, subprocess.SubprocessError) as e:
                LOG.warning("go-validate: build failed: %s", e)
                return out
        else:
            LOG.warning("go-validate: binary absent and cannot build (go=%s src=%s)",
                        bool(go), src.is_dir())
            return out

    out["available"] = True
    try:
        res = subprocess.run(
            [str(binary), "-q", "-allow-disabled", *[str(p) for p in rule_paths]],
            capture_output=True, text=True, timeout=300, check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        LOG.warning("go-validate: run failed: %s", e)
        return out

    # Validator exits non-zero when any rule fails; -q prints failures + summary.
    if res.returncode == 0:
        out["passed"] = len(rule_paths)
    else:
        failures = [ln for ln in res.stdout.splitlines() if "FAIL" in ln.upper()]
        out["failures"] = failures
        out["failed"] = len(failures) if failures else len(rule_paths)
        out["passed"] = max(0, len(rule_paths) - out["failed"])
        LOG.warning("go-validate: %d failure line(s)", len(failures))
    return out


def _enumerate_rules(rule: Path | None, rules_dir: Path | None,
                     batch: Path | None = None, liaprobe_root: Path | None = None) -> list[Path]:
    if rule:
        return [rule.resolve()]
    if rules_dir:
        d = rules_dir.resolve()
        if not d.exists() or not d.is_dir():
            raise SystemExit(f"rules-dir not found: {d}")
        return sorted(p for p in d.glob("*.json") if p.is_file())
    if batch:
        bp = batch.resolve()
        if not bp.exists():
            raise SystemExit(f"batch file not found: {bp}")
        try:
            data = json.loads(bp.read_text())
        except (json.JSONDecodeError, OSError) as e:
            raise SystemExit(f"batch file invalid JSON: {e}")
        if data.get("schema") != "lia-enrich-batch-v1":
            raise SystemExit(f"batch schema mismatch: got {data.get('schema')!r}, want lia-enrich-batch-v1")
        if liaprobe_root is None:
            raise SystemExit("--liaprobe-root required when using --batch")
        seen: set[Path] = set()
        out: list[Path] = []
        for action_type, entries in (data.get("batches") or {}).items():
            for e in entries:
                rf = e.get("rule_file")
                if not rf:
                    continue
                abs_path = (liaprobe_root / rf).resolve()
                if abs_path in seen:
                    continue
                if not abs_path.exists():
                    continue
                seen.add(abs_path)
                out.append(abs_path)
        return sorted(out)
    raise SystemExit("--rule, --rules-dir or --batch required")


# Canonical vendor resolution (LiaProbe <-> threat-intel sync)

_VENDOR_RESOLVER_CACHE: dict[str, dict | None] = {}


def _resolve_and_inject_canonical_vendor(rp: Path) -> dict | None:
    """Resolve canonical vendor for a rule and inject into _meta_enrichment.

    Reads cpe23_template, resolves via vendor_alias table (exact + pg_trgm),
    writes the result into rule._meta_enrichment.canonical_vendor atomically.

    Idempotent: skips PG round-trip when canonical_vendor already populated
    AND the cpe23_template hasn't changed since last resolution.

    Returns the canonical_vendor dict or None when no match / PG unavailable.
    """
    try:
        rule = json.loads(rp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        LOG.warning("[%s] cannot read rule for vendor resolution: %s", rp.name, e)
        return None

    cpe_vendor = el.extract_cpe_vendor(rule)
    if not cpe_vendor:
        return None
    cpe_product = el.extract_cpe_product(rule)

    cache_key = f"{cpe_vendor}|{cpe_product}"

    # Idempotent shortcut: already resolved against same (vendor, product) tokens
    existing = rule.get("_meta_enrichment", {}).get("canonical_vendor")
    if existing and existing.get("cpe_vendor_input") == cpe_vendor \
            and existing.get("cpe_product_input") == cpe_product \
            and "lia_signature_key" in existing:
        return existing

    # Process-local cache (avoid hitting PG once per cycle for same key)
    if cache_key in _VENDOR_RESOLVER_CACHE:
        resolved = _VENDOR_RESOLVER_CACHE[cache_key]
    else:
        try:
            with el.PGClient() as pg:
                resolver = el.CanonicalVendorResolver(pg)
                # Try full personalized resolve first (alias_chain + product_id +
                # sub_product flag + lia_signature_key). Falls back to legacy
                # resolve() (vendor_alias-only with fuzzy_trgm) when full path
                # returns None -- captures the cases where vendor exists in
                # vendor_alias but NVD product table has no product row.
                resolved = resolver.resolve_full(cpe_vendor, cpe_product)
                if resolved is None:
                    legacy = resolver.resolve(cpe_vendor)
                    if legacy is not None:
                        resolved = {
                            "method": "alias_only",
                            "vendor_id": legacy["vendor_id"],
                            "vendor_name": legacy["vendor_name"],
                            "product_id": None,
                            "product_name_db": None,
                            "sub_product": False,
                            "alias_chain": [{
                                "alias_name": legacy["alias_name"],
                                "alias_source": legacy["alias_source"],
                                "alias_type": legacy["alias_type"],
                                "confidence_score": legacy["confidence_score"],
                            }],
                            "confidence": legacy["confidence_score"],
                            "ambiguous": False,
                            "lia_signature_key": f"lia_v{legacy['vendor_id']}",
                            "resolved_at": legacy["resolved_at"],
                            "_legacy_resolved_via": legacy["resolved_via"],
                            "_legacy_similarity": legacy.get("similarity"),
                        }
        except el.DependencyMissingError as e:
            LOG.warning("[%s] vendor resolve unavailable: %s", rp.name, e)
            return None
        _VENDOR_RESOLVER_CACHE[cache_key] = resolved

    if resolved is None:
        # Persist a "no match" sentinel so we don't re-query on every run
        sentinel = {
            "cpe_vendor_input": cpe_vendor,
            "cpe_product_input": cpe_product,
            "vendor_id": None,
            "vendor_name": None,
            "product_id": None,
            "lia_signature_key": None,
            "resolved_via": "no_match",
            "resolved_at": el.utc_now_iso(),
        }
        meta = rule.setdefault("_meta_enrichment", {})
        meta["canonical_vendor"] = sentinel
        el.AtomicJSONWriter.write(rp, rule)
        return sentinel

    payload = {
        **resolved,
        "cpe_vendor_input": cpe_vendor,
        "cpe_product_input": cpe_product,
        "resolved_via": resolved.get("method", "unknown"),
    }
    meta = rule.setdefault("_meta_enrichment", {})
    meta["canonical_vendor"] = payload
    el.AtomicJSONWriter.write(rp, rule)
    return payload


# Procedural mode

def run_procedural(
    rule_paths: Iterable[Path],
    cycles: list[str],
    sm: el.StateManager,
    ew: el.EvidenceWriter,
    handlers: dict,
) -> dict:
    summary = {"rules": []}
    for rp in rule_paths:
        rule_summary = {"rule": str(rp), "cycles": []}
        try:
            with sm.lock(rp) as lock:
                vendor = _resolve_and_inject_canonical_vendor(rp)
                if vendor:
                    rule_summary["canonical_vendor"] = {
                        "vendor_id": vendor.get("vendor_id"),
                        "vendor_name": vendor.get("vendor_name"),
                        "resolved_via": vendor.get("resolved_via"),
                        "confidence_score": vendor.get("confidence_score"),
                    }
                for cid in cycles:
                    handler = handlers.get(cid)
                    if handler is None:
                        rule_summary["cycles"].append({"cycle": cid, "status": "no_handler"})
                        LOG.warning("[%s] no handler for %s", rp.name, cid)
                        continue
                    rule_data = json.loads(rp.read_text(encoding="utf-8"))
                    try:
                        success, applied_diff, cycle_summary = handler(rp, rule_data, ew, sm, lock)
                    except Exception as e:
                        rule_summary["cycles"].append({
                            "cycle": cid,
                            "status": "raised",
                            "error": str(e),
                            "trace": traceback.format_exc().splitlines()[-3:],
                        })
                        LOG.error("[%s] %s raised: %s", rp.name, cid, e)
                        continue
                    rule_summary["cycles"].append({
                        "cycle": cid,
                        "status": "ok" if success else "skipped",
                        "summary": cycle_summary,
                    })
                    LOG.info("[%s] %s: %s", rp.name, cid, "OK" if success else "SKIP")
        except el.EnrichError as e:
            rule_summary["error"] = str(e)
            LOG.error("[%s] lock/error: %s", rp.name, e)
        try:
            final = json.loads(rp.read_text(encoding="utf-8"))
            rule_summary["transformative_score"] = compute_transformative_score(final)
        except OSError:
            pass
        summary["rules"].append(rule_summary)
    return summary


# Agentic mode

def run_agentic(
    rule_paths: Iterable[Path],
    sm: el.StateManager,
    ew: el.EvidenceWriter,
    handlers: dict,
    target_score: float,
    max_iter: int,
    onyphe_dataset_path: Path | None,
    journal: el.StructuredLogger | None,
) -> dict:
    summary = {"rules": []}
    for rp in rule_paths:
        # Canonical vendor resolution (LiaProbe <-> threat-intel sync) before OODA
        vendor = _resolve_and_inject_canonical_vendor(rp)
        engine = OODAEngine(
            rule_path=rp,
            state_manager=sm,
            evidence_writer=ew,
            cycle_handlers=handlers,
            target_score=target_score,
            max_iter=max_iter,
            onyphe_dataset_path=onyphe_dataset_path,
            journal=journal,
        )
        try:
            result: OODAResult = engine.run()
        except Exception as e:
            summary["rules"].append({
                "rule": str(rp), "error": str(e),
                "trace": traceback.format_exc().splitlines()[-3:],
            })
            LOG.error("[%s] OODA raised: %s", rp.name, e)
            continue
        rule_summary = {
            "rule": str(rp),
            "verdict": result.verdict.value,
            "iterations": result.iterations,
            "completed": result.cycles_completed,
            "skipped": result.cycles_skipped,
            "failed": result.cycles_failed,
            "final_score": result.final_score,
        }
        if vendor:
            rule_summary["canonical_vendor"] = {
                "vendor_id": vendor.get("vendor_id"),
                "vendor_name": vendor.get("vendor_name"),
                "resolved_via": vendor.get("resolved_via"),
                "confidence_score": vendor.get("confidence_score"),
            }
        summary["rules"].append(rule_summary)
        LOG.info("[%s] verdict=%s iter=%d score=%.1f",
                 rp.name, result.verdict.value, result.iterations, result.final_score)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_enrich",
        description="LiaProbe rule enrichment orchestrator (procedural + agentic)",
    )
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--rule", type=Path, help="Path to a single rule.json")
    target.add_argument("--rules-dir", type=Path, help="Directory of rule.json files")
    target.add_argument("--batch", type=Path,
                        help="Path to enrich batch JSON emitted by consume_enrich_queue.py "
                             "(schema lia-enrich-batch-v1). Extracts unique rule_file paths "
                             "and resolves them against --liaprobe-root.")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--cycles", type=str,
        help="Comma-separated cycles (e.g. '4,5,7' or 'cycle_4_cve,cycle_5_eol')",
    )
    mode.add_argument("--ooda", action="store_true", help="Run OODA agentic loop")
    mode.add_argument("--from-batch-actions", action="store_true",
                      help="Derive --cycles set from the --batch file action types. "
                           "Inline actions (e.g. cpe23_template_fill) applied first. "
                           "Requires --batch.")

    p.add_argument("--target", type=float, default=70.0,
                   help="OODA target_score (default 70)")
    p.add_argument("--max-iter", type=int, default=12,
                   help="OODA max_iter (default 12)")
    p.add_argument("--onyphe-dataset", type=Path, default=None,
                   help="Path to Onyphe ground-truth dataset (G9 regression check)")
    p.add_argument("--liaprobe-root", type=Path, default=None,
                   help="LiaProbe root (default $LIAPROBE_ROOT or /opt/lia-sec/liaprobe)")
    p.add_argument("--summary", type=Path, default=None,
                   help="Write JSON summary to path")
    p.add_argument("--go-validate", action="store_true",
                   help="After enrichment, run the Go fingerprint validator "
                        "(bin/lia-rule-validate, rebuilt if absent) on the "
                        "enriched rules -- same gate as the pre-commit hook.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    liaprobe_root = (args.liaprobe_root or _resolve_liaprobe_root()).resolve()
    LOG.info("liaprobe_root=%s", liaprobe_root)
    sm, ew = _build_components(liaprobe_root)
    handlers = _load_handlers()
    LOG.info("handlers loaded: %s", sorted(handlers.keys()))

    rules = _enumerate_rules(args.rule, args.rules_dir, args.batch, liaprobe_root)
    LOG.info("rules to enrich: %d", len(rules))

    journal_path = liaprobe_root / "_alire/tracking/liaprobe-enrich-v2/runtime/journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal = el.StructuredLogger(journal_path)

    started = time.time()
    inline_results: list[dict] = []
    if args.from_batch_actions:
        if not args.batch:
            LOG.error("--from-batch-actions requires --batch")
            return 2
        cycle_ids, inline_actions = _derive_cycles_from_batch(args.batch)
        LOG.info("derived cycles from batch: %s (inline actions: %d)",
                 cycle_ids, len(inline_actions))
        for act in inline_actions:
            res = _apply_inline_action(act, liaprobe_root)
            res["pattern_id"] = act.get("pattern_id")
            res["action_type"] = act["action_type"]
            inline_results.append(res)
            LOG.info("inline %s on %s -> %s",
                     act["action_type"], act.get("pattern_id"), res.get("status"))
        if not cycle_ids:
            LOG.warning("no cycle ids derived from batch (only inline actions ran)")
            summary = {"rules": [], "cycles_run": [], "inline_actions": inline_results}
        else:
            summary = run_procedural(rules, cycle_ids, sm, ew, handlers)
            summary["inline_actions"] = inline_results
    elif args.cycles:
        tokens = [t for t in args.cycles.split(",") if t.strip()]
        cycle_ids = []
        for t in tokens:
            cid = _resolve_cycle_id(t)
            if cid is None:
                LOG.error("unknown cycle: %s", t)
                return 2
            cycle_ids.append(cid)
        summary = run_procedural(rules, cycle_ids, sm, ew, handlers)
    else:
        summary = run_agentic(
            rule_paths=rules,
            sm=sm, ew=ew, handlers=handlers,
            target_score=args.target,
            max_iter=args.max_iter,
            onyphe_dataset_path=args.onyphe_dataset,
            journal=journal,
        )

    elapsed = round(time.time() - started, 2)
    summary["elapsed_seconds"] = elapsed
    summary["mode"] = ("from_batch_actions" if args.from_batch_actions
                      else ("procedural" if args.cycles else "ooda"))
    LOG.info("done in %.2fs", elapsed)

    if args.go_validate:
        gv = _go_validate(rules, liaprobe_root)
        summary["go_validate"] = gv
        LOG.info("go-validate: available=%s built=%s passed=%d failed=%d",
                 gv["available"], gv["built"], gv["passed"], gv["failed"])

    try:
        import update_enriched_index as _uei
        _uei.main(["--liaprobe-root", str(liaprobe_root)])
    except Exception as e:
        LOG.warning("ENRICHED_RULES.md auto-update failed: %s", e)

    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        LOG.info("summary written to %s", args.summary)
    else:
        print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
