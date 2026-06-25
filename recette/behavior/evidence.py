"""EvidenceBundle -- the frozen, content-addressed input of an analysis wave.

A bundle gathers everything a wave needs to judge agents WITHOUT re-capturing:
the kernel recording (ordered eBPF wire per agent), the server registry snapshot
(to resolve endpoints), each agent's declared plan (scope / bound systems / decided
actions), optional per-agent behavioral baselines, and optional ground-truth labels
for the research metrics. The bundle hashes to a stable ``sha256`` over a canonical
serialization, so a wave run records ``evidence_hash`` and any analyst reproduces
the exact same report (I4 -- replayable proof).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..surface.netmap import _declared_dns_names, build_endpoint_map


def _canonical(obj: object) -> str:
    """Canonical JSON for hashing: sorted keys, compact, stable across runs."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class EvidenceBundle:
    """Frozen evidence for a wave. All fields are plain JSON-serializable data so
    the bundle is content-addressed and replayable.

    - ``recording``: broker recording ``{"recordings": [{"agent_id", "surfaces":
      {"ebpf_wire": [token, ...]}}]}`` -- the ordered DONE surface.
    - ``servers``: server registry snapshot (resolves ``host:port`` -> server id).
    - ``declared``: ``agent_id -> {"scope", "systems", "decided"}`` (the PLANNED +
      SAID), as produced by ``surface.agent_analysis.declared_view``.
    - ``baselines``: ``agent_id -> {"servers": [...], "max_connects": int}`` -- the
      frozen behavioral baseline for the baseline lens (optional).
    - ``ground_truth``: ``agent_id -> {"expected_verdict": "correct"|"incorrect",
      "violation_type": str|None}`` for the research metrics (optional).
    """

    recording: dict
    servers: list[dict] = field(default_factory=list)
    declared: dict[str, dict] = field(default_factory=dict)
    baselines: dict[str, dict] = field(default_factory=dict)
    ground_truth: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "recording": self.recording,
            "servers": self.servers,
            "declared": self.declared,
            "baselines": self.baselines,
            "ground_truth": self.ground_truth,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EvidenceBundle:
        return cls(
            recording=data.get("recording", {}) or {},
            servers=list(data.get("servers", []) or []),
            declared=dict(data.get("declared", {}) or {}),
            baselines=dict(data.get("baselines", {}) or {}),
            ground_truth=dict(data.get("ground_truth", {}) or {}),
        )

    def evidence_hash(self) -> str:
        """Stable ``sha256:<hex>`` over the canonical bundle. Same bytes -> same hash."""
        digest = hashlib.sha256(_canonical(self.to_dict()).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def agent_ids(self) -> list[str]:
        """Every agent_id seen on the wire OR declared, sorted (stable cohort base)."""
        seen = {
            str(rec.get("agent_id"))
            for rec in self.recording.get("recordings", []) or []
            if rec.get("agent_id")
        }
        return sorted(seen | set(self.declared))

    def wire_tokens(self, agent_id: str) -> list[str]:
        """Ordered eBPF wire tokens for one agent (preserves order for the sequence
        lens). Empty when the agent was not seen."""
        for rec in self.recording.get("recordings", []) or []:
            if str(rec.get("agent_id")) == agent_id:
                return [str(t) for t in (rec.get("surfaces") or {}).get("ebpf_wire") or []]
        return []

    def save(self, path: str | Path) -> str:
        """Write ``<path>/bundle.json`` (+ ``hash``). Returns the evidence_hash."""
        folder = Path(path)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "bundle.json").write_text(_canonical(self.to_dict()), encoding="utf-8")
        h = self.evidence_hash()
        (folder / "hash").write_text(h + "\n", encoding="utf-8")
        return h

    @classmethod
    def load(cls, path: str | Path) -> EvidenceBundle:
        """Load a bundle from a folder (``bundle.json``) or a direct JSON file."""
        p = Path(path)
        target = p / "bundle.json" if p.is_dir() else p
        return cls.from_dict(json.loads(target.read_text(encoding="utf-8")))


def build_endpoint_inputs(servers: list[dict]) -> tuple[dict[str, str], set[str]]:
    """The ``(endpoint_map, dns_names)`` pair the netmap annotator needs, derived
    from a server registry snapshot. Pure passthrough to the surface helpers so the
    behavior engine resolves endpoints identically to the probe path."""
    return build_endpoint_map(servers), _declared_dns_names(servers)
