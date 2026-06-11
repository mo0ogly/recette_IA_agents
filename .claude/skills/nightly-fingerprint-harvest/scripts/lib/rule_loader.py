"""Load LiaProbe fingerprint JSON rules across the 4 target directories."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# Target directories. Order matters: lia first (highest priority).
TARGET_DIRS = [
    "patterns/lia",
    "patterns/web-signatures",
    "patterns/banner-signatures",
    "patterns/service-detectors",
    "patterns/tcp-probes",
]
# Subdirectories under a target dir that hold non-rule artifacts and must
# be skipped (e.g. raw capture HTML, manifest files).
EXCLUDE_SUBDIRS = {
    "captures", "evidence", "_archive", "_archive_c26", "archive", "_tmp",
}
LIAPROBE_ROOT = Path("/opt/lia-sec/liaprobe")
REBUILD_MASTER = Path(
    "/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild/master_data"
)


@dataclass
class Rule:
    rule_id: str
    path: Path
    data: dict
    probes: list[dict] = field(default_factory=list)
    default_ports: list[int] = field(default_factory=list)
    has_artifacts_capture: bool = False

    @property
    def vendor(self) -> str:
        return str(self.data.get("vendor", ""))

    @property
    def product(self) -> str:
        return str(self.data.get("product", ""))

    @property
    def taxonomy_code(self) -> str:
        return str(self.data.get("taxonomy_code", ""))

    @property
    def query_seed(self) -> str:
        """Suggested query string for external sources (vendor + product)."""
        parts = [self.vendor, self.product]
        seed = " ".join(p for p in parts if p).strip()
        if seed:
            return seed
        # Fallbacks when vendor/product not present (common in web-signatures).
        if self.taxonomy_code:
            return self.taxonomy_code.replace("_", " ")
        return self.rule_id.replace("_", " ")

    @property
    def literal_needles(self) -> list[str]:
        """Literal strings useful for source-code search engines (publicwww)."""
        needles: list[str] = []
        for probe in self.probes:
            for matcher in probe.get("matchers", []):
                if matcher.get("match_type") in ("contains", "exact"):
                    val = str(matcher.get("value", "")).strip()
                    if val:
                        needles.append(val)
                elif matcher.get("match_type") == "regex":
                    val = str(matcher.get("value", ""))
                    # Keep regexes that look like a plain literal (no metachars).
                    if val and not any(c in val for c in r"\.*+?()[]{}|^$"):
                        needles.append(val.strip())
        # Dedup, preserve order.
        seen: set[str] = set()
        ordered: list[str] = []
        for n in needles:
            if n not in seen and len(n) >= 4:
                seen.add(n)
                ordered.append(n)
        return ordered[:5]


def _load_one(path: Path) -> Optional[Rule]:
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    rule_id = str(data.get("id") or path.stem)
    probes = list(data.get("probes", []))
    ports = list(data.get("default_ports", []))
    has_capture = bool(
        data.get("artifacts", {}).get("html_sha256")
        or data.get("artifacts", {}).get("favicon_sha256")
    )
    return Rule(
        rule_id=rule_id,
        path=path,
        data=data,
        probes=probes,
        default_ports=ports,
        has_artifacts_capture=has_capture,
    )


def iter_rules(extra_dirs: Optional[Iterable[Path]] = None) -> Iterable[Rule]:
    """Iterate all rules across the target dirs.

    Skip files that fail to parse. Caller filters further by status.
    """
    bases: list[Path] = []
    for rel in TARGET_DIRS:
        d = LIAPROBE_ROOT / rel
        if d.is_dir():
            bases.append(d)
    if REBUILD_MASTER.is_dir():
        bases.append(REBUILD_MASTER)
    if extra_dirs:
        bases.extend(Path(p) for p in extra_dirs)

    for base in bases:
        # Top-level rules first (consistent ordering across dirs).
        for path in sorted(base.glob("*.json")):
            rule = _load_one(path)
            if rule is not None:
                yield rule
        # Recurse one level into known rule subdirectories, skipping
        # non-rule folders (captures/, _archive/, etc.).
        for sub in sorted(p for p in base.iterdir() if p.is_dir()):
            if sub.name in EXCLUDE_SUBDIRS:
                continue
            for path in sorted(sub.glob("*.json")):
                rule = _load_one(path)
                if rule is not None:
                    yield rule


def needs_capture(rule: Rule) -> bool:
    """Decide whether a rule needs a fresh nightly capture.

    Criteria (any true):
      - artifacts.html_sha256 missing
      - artifacts.capture_url missing or generic placeholder
      - _lia_independent_authoring.http_gate.verified is false / absent
      - rule lists at least one L7_HTTP probe (we can capture)
    """
    artifacts = rule.data.get("artifacts", {}) or {}
    if not artifacts.get("html_sha256"):
        return True
    capture_url = artifacts.get("capture_url", "") or ""
    if not capture_url or capture_url.startswith("documented_"):
        return True
    gate = rule.data.get("_lia_independent_authoring", {}).get("http_gate", {})
    if gate.get("verified") is not True:
        return True
    return any(p.get("layer") in ("L7_HTTP", "L4_TCP") for p in rule.probes)
