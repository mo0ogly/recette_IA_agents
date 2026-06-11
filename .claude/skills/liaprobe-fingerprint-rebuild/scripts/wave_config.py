#!/usr/bin/env python3
# wave_config.py -- Schema constants and runtime configuration for the nightly fingerprint batch.
from dataclasses import dataclass
from typing import Callable


# ---------------------------------------------------------------------------
# Schema template (used in prompt)
# ---------------------------------------------------------------------------

SCHEMA_EXAMPLE = """{
  "$schema": "lia-fingerprint-v2-independent",
  "id": "lowercase_id",
  "version": "2.0.0",
  "enabled": true,
  "taxonomy_code": "UPPER_CODE",
  "taxonomy_name": "Human Readable Name",
  "product": "Product Name",
  "vendor": "Vendor Corp",
  "vendor_website": "https://vendor.com/",
  "default_ports": [80, 443],
  "probes": [{
    "id": "lia_<id>_http",
    "layer": "L7_HTTP",
    "method": "GET",
    "path": "/",
    "follow_redirects": true,
    "matchers": [
      {
        "target": "header",
        "field": "server",
        "match_type": "regex",
        "value": "(?i)product-server",
        "confidence_delta": 0.75
      }
    ]
  }],
  "base_confidence": 0.0,
  "confidence_threshold": 0.65,
  "tags": ["category-tag"],
  "artifacts": {
    "html_sha256": null,
    "favicon_sha256": null,
    "favicon_mmh3": null,
    "headers_sha256": null,
    "capture_url": "https://vendor.com/docs/http-headers",
    "observation_provenance": "documented_default_behavior",
    "capture_date": "DATE"
  },
  "_lia_independent_authoring": {
    "review_date": "DATE",
    "operator": "nightly-batch-DATE",
    "method": "direct_public_observation",
    "vendor_website": "https://vendor.com/",
    "rationale": "Source: [URL] -- [documented behavior observed]",
    "false_positive_check": "Pattern tested against nginx/apache/cloudflare -- NEGATIVE",
    "third_party_catalog_references_consulted": "NONE -- pattern authored from public observation",
    "supersedes_prior_rule": "patterns/web-signatures/PRODUCT.json"
  }
}"""


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "$schema", "id", "version", "enabled", "taxonomy_code", "taxonomy_name",
    "product", "vendor", "vendor_website", "default_ports", "probes",
    "base_confidence", "confidence_threshold", "tags", "artifacts",
    "_lia_independent_authoring",
]
REQUIRED_ARTIFACTS = ["capture_url", "observation_provenance", "capture_date"]
REQUIRED_AUTHORING = [
    "review_date", "operator", "method", "rationale",
    "false_positive_check", "third_party_catalog_references_consulted",
]

OBSOLETE_SIGNALS = [
    "abandoned", "obsolete", "discontinued", "defunct",
    "no web presence", "no longer maintained", "unmaintained",
    "project dead", "end of life", "eol", "not found", "404",
    "domain expired", "shut down", "shutting down",
]


# ---------------------------------------------------------------------------
# WaveConfig: bundles runtime config + filesystem/state callbacks.
# Callbacks are injected by nightly_fingerprint_batch so wave_processor
# has zero filesystem imports and remains fully unit-testable.
# ---------------------------------------------------------------------------

@dataclass
class WaveConfig:
    # Runtime config
    n_waves: int
    rules_per_wave: int
    model: str
    escalate_model: str
    dry_run: bool
    run_date: str
    resolve_vendor_url: str  # "heuristic" | "http" | "off"
    claude_bin: str

    # Filesystem/state callbacks (injected by the main script)
    get_products: Callable[[int], list]       # (n) -> list[dict]
    mark_authored: Callable[[str, str], None]  # (code, date) -> None
    mark_deferred: Callable[[str, str, str], None]  # (code, date, reason) -> None
    mark_archived: Callable[[str, str], None]  # (code, date) -> None
    write_rule: Callable[[dict, str, bool], None]  # (rule, code, archived) -> None
    git_commit: Callable[[int, list, list], None]  # (wave, authored, archived) -> None
    log: Callable[[str], None]               # (msg) -> None
