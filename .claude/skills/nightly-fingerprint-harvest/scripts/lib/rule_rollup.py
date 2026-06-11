"""Per-rule rollup package for the recette step.

At the end of processing one rule, produce inside
<session_root>/nightly/<DATE>/<RULE_ID>/:

  rule_snapshot.json    -- frozen copy of the source JSON rule
  index.json            -- machine-readable consolidated summary
  INDEX.md              -- human-readable summary (recette opens this)
  proposed_patch.json   -- only if best_score >= rule.confidence_threshold,
                           contains the artifacts/http_gate diff suggested
                           for the source rule.

If no capture happened (e.g. quota exhausted on all sources) no directory
is created -- responsibility of evidence_writer to keep it empty-free.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


def _read_meta(folder: Path) -> Optional[dict]:
    try:
        return json.loads((folder / "meta.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _read_derived(folder: Path) -> Optional[dict]:
    try:
        return json.loads((folder / "derived.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _detect_drift(rule_data: dict, captures: list[dict]) -> bool:
    """Drift = rule already has an html_sha256 different from every fresh
    capture sha256.
    """
    existing = (rule_data.get("artifacts") or {}).get("html_sha256")
    if not existing:
        return False
    fresh_hashes = {c["meta"].get("html_sha256") for c in captures if c["meta"]}
    fresh_hashes.discard(None)
    if not fresh_hashes:
        return False
    return existing not in fresh_hashes


def _build_patch(rule_data: dict, best_capture: dict) -> dict:
    """Build a JSON patch proposal for the source rule.

    Returns the *full* proposed artifacts + http_gate blocks. The caller
    (downstream recette / APEX cycle) applies them when accepted.
    """
    meta = best_capture["meta"]
    return {
        "_proposed_at": datetime.now(timezone.utc).isoformat(),
        "_basis": {
            "source": meta.get("source"),
            "host": meta.get("host"),
            "capture_url": meta.get("capture_url"),
            "http_status": meta.get("http_status"),
            "match_score": best_capture["derived"].get("match_score"),
        },
        "patch": {
            "artifacts": {
                "html_sha256": meta.get("html_sha256"),
                "headers_sha256": meta.get("headers_sha256"),
                "capture_url": meta.get("capture_url"),
                "capture_date": str(date.today()),
                "observation_provenance": "nightly_harvest_external_source",
            },
            "_lia_independent_authoring.http_gate": {
                "date": str(date.today()),
                "verified": True,
                "http_status": meta.get("http_status") or 0,
                "note": (
                    f"Verified via {meta.get('source')} capture of {meta.get('host')} "
                    f"(score={best_capture['derived'].get('match_score'):.2f})"
                ),
            },
            "_drop_keys": ["_lia_independent_authoring.wild_traffic_unconfirmed"],
        },
    }


def _markdown_index(rule_data: dict, captures: list[dict], best: Optional[dict], drift: bool) -> str:
    rid = rule_data.get("id") or "unknown"
    vendor = rule_data.get("vendor") or "(none)"
    product = rule_data.get("product") or "(none)"
    threshold = float(rule_data.get("confidence_threshold") or 0.6)

    lines = [
        f"# Nightly evidence -- {rid}",
        "",
        f"- Vendor: **{vendor}**",
        f"- Product: **{product}**",
        f"- Confidence threshold: {threshold}",
        f"- Captures: {len(captures)}",
        f"- Drift detected: {drift}",
        "",
        "## Per-capture summary",
        "",
        "| Source | Host | Port | HTTP | Score | Matched | Hash (body) |",
        "|--------|------|------|------|-------|---------|-------------|",
    ]
    for cap in captures:
        m = cap["meta"]
        d = cap["derived"]
        lines.append(
            f"| {m.get('source')} | {m.get('host')} | {m.get('enriched',{}).get('port')} | "
            f"{m.get('http_status')} | {d.get('match_score', 0):.2f} | "
            f"{d.get('any_probe_matched')} | "
            f"{(m.get('html_sha256') or '')[:12]} |"
        )

    if best:
        m = best["meta"]
        en = m.get("enriched") or {}
        lines += [
            "",
            "## Best capture",
            "",
            f"- Source: {m.get('source')}",
            f"- Host: {m.get('host')}",
            f"- URL: {m.get('capture_url')}",
            f"- HTTP status: {m.get('http_status')}",
            f"- html_sha256: `{m.get('html_sha256')}`",
            f"- headers_sha256: `{m.get('headers_sha256')}`",
            f"- Banner: `{m.get('banner') or 'n/a'}`",
            "",
            "### Enriched metadata",
            "",
            f"- IP/Port: {en.get('ip')}:{en.get('port')}",
            f"- Hostname: {en.get('hostname')}",
            f"- ASN: {en.get('asn')} ({en.get('asn_org')})",
            f"- ISP: {en.get('isp')}",
            f"- Geo: {en.get('city')}, {en.get('region')}, {en.get('country')} ({en.get('country_code')})",
            f"- Server header: `{en.get('server_header')}`",
            f"- Content-Type: `{en.get('content_type')}`",
            f"- JARM: `{en.get('jarm')}`",
            f"- JA3: `{en.get('ja3')}`",
            f"- TLS issuer: `{en.get('tls_issuer')}`",
            f"- TLS subject CN: `{en.get('tls_subject_cn')}`",
            f"- TLS SAN count: {len(en.get('tls_subject_alt_names') or [])}",
            f"- Software: {en.get('software_vendor')} / {en.get('software_product')} {en.get('software_version')}",
            f"- CPE: `{en.get('cpe')}`",
            f"- Favicon mmh3: {en.get('favicon_hash_mmh3')}",
            f"- Last seen: {en.get('last_seen_iso')}",
            "",
            "### Matched matchers",
            "",
        ]
        for matched in best["derived"].get("matched_matchers", []):
            lines.append(
                f"- `{matched.get('match_type')}` "
                f"target=`{matched.get('target')}` "
                f"value=`{matched.get('value')}` "
                f"+{matched.get('confidence_delta')} "
                f"version_extract=`{matched.get('version_extract') or ''}`"
            )

    lines += [
        "",
        "## How to recette this rule",
        "",
        "1. Inspect each capture folder (raw.bin / headers.txt / derived.json)",
        "2. Confirm `rule_snapshot.json` matches the current source rule",
        "3. If satisfied, apply `proposed_patch.json` to the source rule",
        "4. Run `/recette-lia-rule` on the patched rule",
        "5. If 164 checks PASS: commit; otherwise REPLAN",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
    ]
    return "\n".join(lines)


def finalize(
    session_root: Path,
    run_date: str,
    rule_id: str,
    rule_data: dict,
    rule_source_path: Path,
) -> dict:
    """Build the rollup for one rule. Returns a summary dict.

    summary = {
       "rule_id": ...,
       "captures": int,
       "best_score": float,
       "best_source": str|null,
       "drift_detected": bool,
       "promotion_ready": bool,
       "rollup_dir": str|null,
    }
    """
    rule_dir = session_root / "nightly" / run_date / rule_id
    summary = {
        "rule_id": rule_id,
        "captures": 0,
        "best_score": 0.0,
        "best_source": None,
        "drift_detected": False,
        "promotion_ready": False,
        "rollup_dir": None,
    }
    if not rule_dir.is_dir():
        return summary

    captures: list[dict] = []
    for sub in sorted(rule_dir.iterdir()):
        if not sub.is_dir():
            continue
        meta = _read_meta(sub)
        derived = _read_derived(sub)
        if meta is None or derived is None:
            continue
        captures.append({
            "folder": str(sub.relative_to(session_root)),
            "meta": meta,
            "derived": derived,
        })

    if not captures:
        return summary

    threshold = float(rule_data.get("confidence_threshold") or 0.6)
    best = max(captures, key=lambda c: float(c["derived"].get("match_score") or 0))
    best_score = float(best["derived"].get("match_score") or 0)
    drift = _detect_drift(rule_data, captures)
    promotion_ready = best_score >= threshold and not drift

    # Persist artefacts.
    (rule_dir / "rule_snapshot.json").write_text(
        json.dumps({
            "source_path": str(rule_source_path),
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "rule": rule_data,
        }, indent=2)
    )
    index = {
        "rule_id": rule_id,
        "run_date": run_date,
        "captures_count": len(captures),
        "best_score": best_score,
        "best_source": best["meta"].get("source"),
        "best_host": best["meta"].get("host"),
        "confidence_threshold": threshold,
        "promotion_ready": promotion_ready,
        "drift_detected": drift,
        "captures": [
            {
                "folder": c["folder"],
                "source": c["meta"].get("source"),
                "host": c["meta"].get("host"),
                "http_status": c["meta"].get("http_status"),
                "html_sha256": c["meta"].get("html_sha256"),
                "match_score": c["derived"].get("match_score"),
                "any_probe_matched": c["derived"].get("any_probe_matched"),
            }
            for c in captures
        ],
    }
    (rule_dir / "index.json").write_text(json.dumps(index, indent=2))
    (rule_dir / "INDEX.md").write_text(_markdown_index(rule_data, captures, best, drift))
    if promotion_ready:
        (rule_dir / "proposed_patch.json").write_text(
            json.dumps(_build_patch(rule_data, best), indent=2)
        )

    summary.update({
        "captures": len(captures),
        "best_score": best_score,
        "best_source": best["meta"].get("source"),
        "drift_detected": drift,
        "promotion_ready": promotion_ready,
        "rollup_dir": str(rule_dir.relative_to(session_root)),
    })
    return summary
