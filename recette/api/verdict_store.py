"""Verdict submissions persistence + pure ground-truth judge.

External discovery/identification tools POST their results; each result is
judged against the agent's stored ground_truth block (config store) and the
judged submission is persisted here. Storage is one plain JSON file with
atomic writes (temp + os.replace), mirroring the campaign store.

The judge is a pure function (I4): same ground truth + same result => same
verdict. No clock, no randomness, no I/O.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

VERDICTS_SCHEMA_VERSION = "1.0"


def default_verdicts_path() -> Path:
    env = os.environ.get("AGENTRAIL_VERDICTS_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "data" / "verdicts.json"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def judge(ground_truth: dict, result: dict, evidence_event_ids: list[str]) -> dict:
    """Compare one tool result against one agent's ground truth.

    Only the fields declared in the ground truth are checked (partial ground
    truth is allowed). An empty ground truth yields SKIP, never PASS by
    vacuity: a submission cannot pass on an agent that declares nothing.
    """
    checks: dict[str, bool] = {}
    if "detectable" in ground_truth:
        checks["detected"] = result.get("detected") == ground_truth["detectable"]
    if "expected_verdict" in ground_truth:
        checks["verdict"] = result.get("verdict") == ground_truth["expected_verdict"]
    if "expected_identity" in ground_truth:
        checks["identity_claim"] = result.get("identity") == ground_truth["expected_identity"]
    for dim, expected in (ground_truth.get("dimensions") or {}).items():
        checks[f"dimension:{dim}"] = (result.get("dimensions") or {}).get(dim) == expected
    if not checks:
        status = "SKIP"
    elif all(checks.values()):
        status = "PASS"
    else:
        status = "FAIL"
    return {
        "status": status,
        "checks": checks,
        "expected": ground_truth,
        "observed": result,
        "evidence_event_ids": evidence_event_ids,
    }


class VerdictStore:
    """JSON-backed, append-only list of judged verdict submissions."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_verdicts_path()

    def _read(self) -> dict:
        if not self.path.exists():
            return {"schema_version": VERDICTS_SCHEMA_VERSION, "submissions": []}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("submissions", [])
        return data

    def append(self, submission: dict) -> dict:
        data = self._read()
        data["submissions"].append(submission)
        _atomic_write(self.path, json.dumps(data, indent=2) + "\n")
        return submission

    def latest(self) -> dict | None:
        submissions = self._read()["submissions"]
        return submissions[-1] if submissions else None

    def history(self) -> list[dict]:
        return self._read()["submissions"]
