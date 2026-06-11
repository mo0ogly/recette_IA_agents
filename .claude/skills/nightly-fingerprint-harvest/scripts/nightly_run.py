#!/usr/bin/env python3
"""Nightly fingerprint harvest orchestrator.

Workflow:
  1. Load JSON rules from patterns/lia, web-signatures, banner-signatures,
     and the rebuild master_data dir.
  2. Filter rules that still need a fresh capture (needs_capture()).
  3. For each rule, iterate enabled collectors in priority order.
     - Skip collector if quota exhausted (quota_tracker).
     - Skip collector if auth not configured (env vars).
  4. Run the rule's probes against each capture (match_runner).
  5. Write evidence to <session_root>/nightly/<DATE>/<RULE_ID>/<SRC>_<HOSTSHA>/.
  6. Append every capture to <DATE>/nightly_manifest.jsonl.

Output is consumed by APEX cycles / liaprobe-rule-enrich to bump
artifacts.html_sha256, artifacts.capture_url and flip
_lia_independent_authoring.http_gate.verified to true.

Usage:
  python3 scripts/nightly_run.py [--dry-run] [--max-rules N]
                                 [--sources netlas,crtsh,...]
                                 [--session-root PATH]

Exit codes:
  0 - run completed (even partial)
  2 - configuration error (paths missing)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

# Allow running as a standalone script.
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from collectors import REGISTRY  # noqa: E402
from collectors.base import CollectorRequest  # noqa: E402
from lib.evidence_writer import Evidence, write_evidence  # noqa: E402
from lib.http_fetch import fetch_host  # noqa: E402
from lib.match_runner import run_match  # noqa: E402
from lib.quota_tracker import QuotaState, check_budget, record_call  # noqa: E402
from lib.rule_loader import Rule, iter_rules, needs_capture  # noqa: E402
from lib.rule_rollup import finalize as rollup_finalize  # noqa: E402
from lib.rule_tracker import (  # noqa: E402
    RuleVisit,
    is_recently_queried,
    record_visit,
    rebuild_status,
)

DEFAULT_SESSION_ROOT = Path(
    "/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild"
)
# Working free-tier sources only. censys (401 PAT expired), zoomeye (403 / API
# moved to zoomeye.ai), rapid7_sonar (needs RAPID7_SONAR_PATH offline dump) are
# DROPPED from the default after the 2026-06-01 nightly logged them dead on every
# query. Their collectors stay on disk; re-enable any by passing an explicit
# --sources / HARVEST_SOURCES override once fresh credentials are supplied.
DEFAULT_PRIORITY = ["netlas", "crtsh", "publicwww"]
# Full catalogue (incl. credentialled sources) for --sources override reference.
ALL_SOURCES = ["netlas", "crtsh", "publicwww", "censys", "zoomeye", "rapid7_sonar"]


def _select_rules(max_rules: int, session_root: Path, cooldown_days: int) -> list[Rule]:
    """Select rules to harvest tonight.

    Filter chain:
      1. needs_capture()       -- rule still lacks live evidence
      2. NOT recently queried  -- respect cooldown to spread load over time

    Order: vendor, product, rule_id (stable, deterministic).
    """
    candidates: list[Rule] = []
    for rule in iter_rules():
        if not needs_capture(rule):
            continue
        if cooldown_days > 0 and is_recently_queried(session_root, rule.rule_id, cooldown_days):
            continue
        candidates.append(rule)
    candidates.sort(key=lambda r: (r.vendor.lower(), r.product.lower(), r.rule_id))
    return candidates[:max_rules] if max_rules > 0 else candidates


def _build_request(rule: Rule, max_hosts: int) -> CollectorRequest:
    return CollectorRequest(
        rule_id=rule.rule_id,
        vendor=rule.vendor,
        product=rule.product,
        taxonomy_code=rule.taxonomy_code,
        query_seed=rule.query_seed,
        literal_needles=rule.literal_needles,
        ports=rule.default_ports or [],
        max_hosts=max_hosts,
    )


def run(
    session_root: Path,
    sources: list[str],
    max_rules: int,
    max_hosts: int,
    dry_run: bool,
    cooldown_days: int,
) -> int:
    log = logging.getLogger("nightly")
    state_dir = session_root / "nightly" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    quota_path = state_dir / "quotas.json"
    state = QuotaState.load(quota_path)
    run_date = date.today().isoformat()

    rules = _select_rules(max_rules, session_root, cooldown_days)
    log.info("rules selected: %d (max=%d, cooldown=%dd)", len(rules), max_rules, cooldown_days)

    total_captures = 0
    promotion_ready_count = 0
    drift_count = 0
    started = time.time()

    for rule in rules:
        log.info("rule %s vendor=%r product=%r", rule.rule_id, rule.vendor, rule.product)
        request = _build_request(rule, max_hosts=max_hosts)
        visit = RuleVisit(rule_id=rule.rule_id, run_date=run_date)
        rule_captures = 0
        best_score = 0.0
        any_probe_matched = False

        for source in sources:
            collector_cls = REGISTRY.get(source)
            if collector_cls is None:
                log.warning("unknown collector %s", source)
                continue
            collector = collector_cls()
            visit.sources_attempted.append(source)
            if not collector.is_configured():
                log.info("  skip %s (missing auth env)", source)
                continue
            allowed, reason = check_budget(state, source)
            if not allowed:
                log.info("  skip %s (%s)", source, reason)
                continue

            if dry_run:
                log.info("  dry-run %s would query for %s", source, rule.query_seed)
                continue

            try:
                results = collector.search(request)
            except Exception as exc:
                log.error("  %s raised: %s", source, exc)
                record_call(state, source, error=str(exc))
                continue

            record_call(state, source)
            source_succeeded = False

            for evidence_record in results:
                if evidence_record.error:
                    log.warning("  %s error: %s", source, evidence_record.error)
                    continue
                if not evidence_record.host:
                    continue
                # Hostname-only sources (crt.sh) return a candidate host with no
                # payload. Fetch it live so the rule's probes have a real body /
                # headers to score against -- without this, match_score is always 0.
                if not evidence_record.body and evidence_record.http_status == 0:
                    fr = fetch_host(evidence_record.host, evidence_record.port or 443)
                    if fr.status:
                        evidence_record.http_status = fr.status
                        evidence_record.headers = fr.headers
                        evidence_record.body = fr.body
                        evidence_record.latency_ms = fr.latency_ms
                        if not evidence_record.capture_url:
                            evidence_record.capture_url = fr.url
                    elif fr.error:
                        log.info("  fetch %s failed: %s", evidence_record.host, fr.error)
                derived = run_match(
                    rule.data,
                    evidence_record.body,
                    evidence_record.headers,
                    evidence_record.banner,
                )
                ev = Evidence(
                    rule_id=rule.rule_id,
                    source=source,
                    host=evidence_record.host,
                    capture_url=evidence_record.capture_url or f"{source}:{evidence_record.host}",
                    http_status=evidence_record.http_status,
                    headers=evidence_record.headers or {},
                    body=evidence_record.body or b"",
                    banner=evidence_record.banner,
                    latency_ms=evidence_record.latency_ms,
                    extra={"raw_record_keys": sorted((evidence_record.raw_record or {}).keys())},
                    raw_record=evidence_record.raw_record or {},
                )
                folder = write_evidence(session_root, run_date, ev, derived)
                total_captures += 1
                rule_captures += 1
                source_succeeded = True
                score = float(derived.get("match_score") or 0.0)
                if score > best_score:
                    best_score = score
                if derived.get("any_probe_matched"):
                    any_probe_matched = True
                log.info("  -> %s match=%s score=%.2f folder=%s",
                         evidence_record.host,
                         derived["any_probe_matched"],
                         derived["match_score"],
                         folder.relative_to(session_root))

            if source_succeeded:
                visit.sources_succeeded.append(source)

        # End of source loop for this rule -- finalize rollup + tracker.
        summary = rollup_finalize(
            session_root=session_root,
            run_date=run_date,
            rule_id=rule.rule_id,
            rule_data=rule.data,
            rule_source_path=rule.path,
        )
        visit.captures_count = rule_captures
        visit.best_match_score = best_score
        visit.any_probe_matched = any_probe_matched
        visit.promotion_ready = summary["promotion_ready"]
        visit.drift_detected = summary["drift_detected"]
        if rule_captures == 0:
            visit.outcome = "no_match" if visit.sources_attempted else "skipped"
        elif visit.drift_detected:
            visit.outcome = "drift"
        elif visit.promotion_ready:
            visit.outcome = "promotion_ready"
        else:
            visit.outcome = "captured_low_score"
        record_visit(session_root, visit)

        if summary["promotion_ready"]:
            promotion_ready_count += 1
        if summary["drift_detected"]:
            drift_count += 1

    state.save(quota_path)
    # Refresh aggregated status cache for downstream tooling.
    rebuild_status(session_root)
    elapsed = int(time.time() - started)
    log.info(
        "done: %d captures (%d promotion-ready, %d drift) over %d rules in %ds",
        total_captures, promotion_ready_count, drift_count, len(rules), elapsed,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-root", default=str(DEFAULT_SESSION_ROOT))
    parser.add_argument("--sources", default=",".join(DEFAULT_PRIORITY))
    parser.add_argument("--max-rules", type=int, default=30)
    parser.add_argument("--max-hosts", type=int, default=3)
    parser.add_argument("--cooldown-days", type=int, default=7,
                        help="Skip rules already queried within N days. 0 disables.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    session_root = Path(args.session_root)
    if not session_root.exists():
        logging.error("session root not found: %s", session_root)
        return 2

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    return run(
        session_root=session_root,
        sources=sources,
        max_rules=args.max_rules,
        max_hosts=args.max_hosts,
        dry_run=args.dry_run,
        cooldown_days=args.cooldown_days,
    )


if __name__ == "__main__":
    raise SystemExit(main())
