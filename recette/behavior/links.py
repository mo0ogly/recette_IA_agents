"""The agent identity map -- links a discovery subject (source repo) to its
runtime evidence so a behavioral wave can be correlated with the static scan.

Hand-maintained ground-truth until P3 builds 1:1 twin evidence bundles. Pure:
loading is a deterministic parse, no clock/random.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LINKS = Path(__file__).resolve().parents[2] / "corpus" / "agent_links.json"


@dataclass(frozen=True)
class Link:
    """One agent's coupling between its discovery subject and its runtime."""

    agent_id: str
    discovery_subject: str | None
    runtime_subject: str | None
    evidence_bundle: str | None
    expected: dict


def load_links(path: Path | str = DEFAULT_LINKS) -> list[Link]:
    """Parse the identity map into Link records, sorted by agent_id (I4)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    links = [
        Link(
            agent_id=str(e["agent_id"]),
            discovery_subject=e.get("discovery_subject"),
            runtime_subject=e.get("runtime_subject"),
            evidence_bundle=e.get("evidence_bundle"),
            expected=e.get("expected") or {},
        )
        for e in data.get("links", [])
    ]
    return sorted(links, key=lambda ln: ln.agent_id)
