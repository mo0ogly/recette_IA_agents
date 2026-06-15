"""Aggregate red-team ScenarioOutcomes into a scorecard + deterministic text.

Pure functions over a list of ScenarioOutcome: counts caught vs missed (a 'miss'
is a scenario whose predicted verdict did not match its expected verdict -- the
recette failed to catch the anomaly or raised a false alarm) and groups by the
OWASP Agentic tag. No clock, no random, stable ordering (I4)."""

from __future__ import annotations

from collections import Counter

from .redteam_recette import ScenarioOutcome


def scorecard(outcomes: list[ScenarioOutcome]) -> dict:
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
                "anomaly_caught": o.anomaly_caught,
                "owasp_asi": o.tags.get("owasp_asi"),
            }
            for o in sorted(outcomes, key=lambda x: x.scenario_id)
        ],
    }


def render(card: dict) -> str:
    lines = [
        "redteam scorecard",
        f"total={card['total']} caught={card['caught']} missed={card['missed']}",
    ]
    for tag, n in card["by_owasp"].items():
        lines.append(f"  {tag}: {n}")
    for row in card["rows"]:
        flag = "OK" if row["anomaly_caught"] else "MISS"
        lines.append(
            f"  [{flag}] {row['scenario_id']} predicted={row['verdict']} "
            f"expected={row['expected_verdict']} violation={row['violation_type']}"
        )
    return "\n".join(lines)
