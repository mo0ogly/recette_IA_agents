"""Evidence storage layout for nightly harvest.

Layout under <session_root>/nightly/<DATE>/<RULE_ID>/<SOURCE>_<HOST_SHA8>/:
  meta.json     -- source_id, capture_url, source_sha256, verified_at, http_status, latency_ms
  raw.bin       -- raw bytes of HTTP response (body) or TCP banner
  headers.txt   -- HTTP response headers (one per line)
  derived.json  -- match result against rule probes (probe_id, matched, version_extract)

Manifest <session_root>/nightly/<DATE>/nightly_manifest.jsonl is append-only;
one line per (rule_id, source, host) tuple. Reader consumers (recette skill,
APEX cycle) iterate the manifest to know what evidence is fresh.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .enriched_meta import enrich as enrich_record


@dataclass
class Evidence:
    rule_id: str
    source: str
    host: str
    capture_url: str
    http_status: int
    headers: dict[str, str]
    body: bytes
    banner: Optional[str] = None
    latency_ms: int = 0
    extra: dict = field(default_factory=dict)
    raw_record: dict = field(default_factory=dict)


def _host_sha8(host: str) -> str:
    return hashlib.sha256(host.encode()).hexdigest()[:8]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_evidence(
    session_root: Path,
    run_date: str,
    evidence: Evidence,
    derived: dict,
) -> Path:
    """Persist evidence + return target directory."""
    base = session_root / "nightly" / run_date / evidence.rule_id
    folder = base / f"{evidence.source}_{_host_sha8(evidence.host)}"
    folder.mkdir(parents=True, exist_ok=True)

    body_sha = _sha256_bytes(evidence.body)
    headers_text = "\n".join(f"{k}: {v}" for k, v in evidence.headers.items())
    headers_sha = _sha256_bytes(headers_text.encode())

    enriched = enrich_record(evidence.source, evidence.raw_record)
    meta = {
        "rule_id": evidence.rule_id,
        "source": evidence.source,
        "host": evidence.host,
        "capture_url": evidence.capture_url,
        "http_status": evidence.http_status,
        "html_sha256": body_sha if evidence.body else None,
        "headers_sha256": headers_sha if evidence.headers else None,
        "banner": evidence.banner,
        "latency_ms": evidence.latency_ms,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "enriched": enriched,
        "extra": evidence.extra,
    }
    # Persist the unmodified raw_record for offline re-enrichment.
    if evidence.raw_record:
        (folder / "raw_record.json").write_text(
            json.dumps(evidence.raw_record, indent=2, default=str)
        )

    (folder / "meta.json").write_text(json.dumps(meta, indent=2))
    if evidence.body:
        (folder / "raw.bin").write_bytes(evidence.body)
    if evidence.headers:
        (folder / "headers.txt").write_text(headers_text)
    (folder / "derived.json").write_text(json.dumps(derived, indent=2))

    manifest_path = session_root / "nightly" / run_date / "nightly_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a") as fh:
        fh.write(json.dumps({
            "rule_id": evidence.rule_id,
            "source": evidence.source,
            "host_sha8": _host_sha8(evidence.host),
            "host": evidence.host,
            "capture_url": evidence.capture_url,
            "http_status": evidence.http_status,
            "html_sha256": meta["html_sha256"],
            "headers_sha256": meta["headers_sha256"],
            "banner_match": derived.get("banner_match", False),
            "any_probe_matched": derived.get("any_probe_matched", False),
            "match_score": derived.get("match_score", 0.0),
            "folder": str(folder.relative_to(session_root)),
            "captured_at": meta["captured_at"],
        }) + "\n")

    return folder
