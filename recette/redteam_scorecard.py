"""Aggregate red-team ScenarioOutcomes into a scorecard + deterministic text.

Pure functions over a list of ScenarioOutcome: counts caught vs missed (a 'miss'
is a scenario whose predicted verdict did not match its expected verdict -- the
recette failed to catch the anomaly or raised a false alarm) and groups by the
OWASP Agentic tag. No clock, no random, stable ordering (I4)."""

from __future__ import annotations

from collections import Counter

from .redteam_recette import ScenarioOutcome


def scorecard(outcomes: list[ScenarioOutcome]) -> dict:
    """Aggregate red-team outcomes into the scorecard dict: total, caught
    (predicted == expected), missed, and the per-OWASP-tag distribution
    (a count of all outcomes carrying each tag, not a catch rate)."""
    by_owasp: Counter[str] = Counter()
    for o in outcomes:
        tag = o.tags.get("owasp_asi")
        if tag:
            by_owasp[tag] += 1
    caught = sum(1 for o in outcomes if o.anomaly_caught)
    return {
        "total": len(outcomes),
        "caught": caught,
        "missed": len(outcomes) - caught,
        "by_owasp": dict(sorted(by_owasp.items())),
        "rows": [
            {
                "scenario_id": o.scenario_id,
                "verdict": o.verdict,
                "expected_verdict": o.expected_verdict,
                "violation_type": o.violation_type,
                "expected_violation_type": o.expected_violation_type,
                "anomaly_caught": o.anomaly_caught,
                "owasp_asi": o.tags.get("owasp_asi"),
            }
            for o in sorted(outcomes, key=lambda x: x.scenario_id)
        ],
    }


def render(card: dict) -> str:
    """Render a scorecard dict (from ``scorecard``) as the human-readable CLI
    block: the total/caught/missed line plus the sorted OWASP distribution."""
    lines = [
        "redteam scorecard",
        f"total={card['total']} caught={card['caught']} missed={card['missed']}",
    ]
    for tag, n in card["by_owasp"].items():
        lines.append(f"  {tag}: {n}")
    for row in card["rows"]:
        flag = "OK" if row["anomaly_caught"] else "MISS"
        lines.append(
            f"  [{flag}] {row['scenario_id']} "
            f"predicted={row['verdict']}/{row['violation_type']} "
            f"expected={row['expected_verdict']}/{row['expected_violation_type']}"
        )
    return "\n".join(lines)
