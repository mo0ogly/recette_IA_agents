"""
quality_gate -- 17 quality gates for OODA loop.

Gates classification:
- PRE-ACT  (G1-G4)  : checked BEFORE running a cycle
- POST-ACT (G5-G10) : checked AFTER cycle execution
- END     (G11-G13) : iteration end (non-blocking)
- STOP    (G14-G17) : loop termination decision

Each gate returns GateResult(status, gate_id, reason, metrics).
PASS = continue, FAIL = block (rollback for POST-ACT, abort for PRE-ACT),
SKIP = N/A in current context.

See _alire/tracking/liaprobe-enrich-v2/OODA_DESIGN.md for full design.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any, Callable

from enrich_lib import (
    CYCLES,
    AtomicJSONWriter,
    CycleStatus,
    EnrichError,
    EvidenceWriter,
    LockManager,
    SchemaValidator,
    StateManager,
    sha256_canonical_json,
    sha256_file,
    utc_now_iso,
)


class GateStatus(enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclasses.dataclass
class GateResult:
    gate_id: str
    status: GateStatus
    reason: str
    metrics: dict = dataclasses.field(default_factory=dict)
    blocking: bool = True

    def is_pass(self) -> bool:
        return self.status == GateStatus.PASS

    def is_fail(self) -> bool:
        return self.status == GateStatus.FAIL

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "reason": self.reason,
            "metrics": self.metrics,
            "blocking": self.blocking,
        }


# ======================================================================
# PRE-ACT gates (G1-G4)
# ======================================================================

def gate_g1_lock_acquired(lock: LockManager | None) -> GateResult:
    """G1 : LockManager has acquired lock (concurrency safe)."""
    held = lock is not None and lock._fd is not None
    return GateResult(
        "G1_lock_acquired",
        GateStatus.PASS if held else GateStatus.FAIL,
        "lock held" if held else "lock not held",
        blocking=True,
    )


def gate_g2_rule_schema_valid(rule_data: dict) -> GateResult:
    """G2 : Rule JSON conforms to lia-fingerprint-v1."""
    try:
        SchemaValidator.validate_fingerprint(rule_data)
        return GateResult(
            "G2_rule_schema_valid",
            GateStatus.PASS,
            "fingerprint schema valid",
            blocking=True,
        )
    except Exception as e:
        return GateResult(
            "G2_rule_schema_valid",
            GateStatus.FAIL,
            f"schema violation: {e}",
            blocking=True,
        )


def gate_g3_dependency_available(
    cycle_id: str,
    dep_check: Callable[[], tuple[bool, str]] | None = None,
) -> GateResult:
    """G3 : Dependency available for cycle (PG up, API reachable, CSV exists).

    dep_check: optional callable returning (ok: bool, reason: str)
    """
    if dep_check is None:
        return GateResult("G3_dependency_available", GateStatus.SKIP, "no check provided")
    try:
        ok, reason = dep_check()
        return GateResult(
            "G3_dependency_available",
            GateStatus.PASS if ok else GateStatus.FAIL,
            reason,
            blocking=True,
        )
    except Exception as e:
        return GateResult(
            "G3_dependency_available",
            GateStatus.FAIL,
            f"dep check raised: {e}",
            blocking=True,
        )


def gate_g4_state_coherent(rule_path: Path, state: dict) -> GateResult:
    """G4 : Rule sha256 in state matches actual rule.json on disk.

    Detects external modification to rule.json since last enrich.
    """
    if not rule_path.exists():
        return GateResult("G4_state_coherent", GateStatus.FAIL, "rule.json missing")
    actual_sha = sha256_file(rule_path)
    expected = state.get("rule", {}).get("rule_sha256_current")
    if expected is None:
        # First time: no expected, always pass
        return GateResult("G4_state_coherent", GateStatus.PASS, "first enrich, no prior sha")
    if actual_sha == expected:
        return GateResult("G4_state_coherent", GateStatus.PASS, "rule sha matches state")
    return GateResult(
        "G4_state_coherent",
        GateStatus.FAIL,
        f"rule modified externally: actual={actual_sha[:8]} expected={expected[:8]}",
        metrics={"actual": actual_sha, "expected": expected},
        blocking=True,
    )


# ======================================================================
# POST-ACT gates (G5-G10)
# ======================================================================

def gate_g5_evidence_sha256(evidence_path: Path, ew: EvidenceWriter) -> GateResult:
    """G5 : Evidence file sha256 matches its raw_data."""
    if not evidence_path.exists():
        return GateResult("G5_evidence_sha256", GateStatus.FAIL, "evidence file missing")
    try:
        if ew.verify_integrity(evidence_path):
            return GateResult("G5_evidence_sha256", GateStatus.PASS, "sha256 valid")
        return GateResult(
            "G5_evidence_sha256",
            GateStatus.FAIL,
            "sha256 mismatch -- evidence tampered",
            blocking=True,
        )
    except Exception as e:
        return GateResult("G5_evidence_sha256", GateStatus.FAIL, f"verify raised: {e}")


def gate_g6_atomic_rule_write(rule_path: Path) -> GateResult:
    """G6 : Rule.json successfully written atomically (no .tmp orphan)."""
    if not rule_path.exists():
        return GateResult("G6_atomic_rule_write", GateStatus.FAIL, "rule.json missing")
    tmp = rule_path.with_suffix(rule_path.suffix + ".tmp")
    if tmp.exists():
        return GateResult(
            "G6_atomic_rule_write",
            GateStatus.FAIL,
            f".tmp orphan exists: {tmp.name}",
            blocking=True,
        )
    try:
        json.loads(rule_path.read_text(encoding="utf-8"))
        return GateResult("G6_atomic_rule_write", GateStatus.PASS, "rule.json valid + no orphan")
    except json.JSONDecodeError as e:
        return GateResult("G6_atomic_rule_write", GateStatus.FAIL, f"rule.json corrupt: {e}")


def _extract_regex_set(rule_data: dict) -> set[str]:
    """Extract all matcher 'value' regex from a fingerprint."""
    regexes: set[str] = set()
    for key in ("banner_matchers", "service_matchers"):
        for m in rule_data.get(key, []):
            if isinstance(m, dict) and isinstance(m.get("value"), str):
                regexes.add(m["value"])
    for p in rule_data.get("probes", []):
        if not isinstance(p, dict):
            continue
        for m in p.get("matchers", []):
            if isinstance(m, dict) and isinstance(m.get("value"), str):
                regexes.add(m["value"])
    return regexes


def gate_g7_regex_preserved(rule_before: dict, rule_after: dict) -> GateResult:
    """G7 : Existing regex/matchers MUST NOT be modified by enrich.

    Enrich only ADDS metadata. Detection logic stays intact.
    """
    before_set = _extract_regex_set(rule_before)
    after_set = _extract_regex_set(rule_after)
    if before_set == after_set:
        return GateResult(
            "G7_regex_preserved",
            GateStatus.PASS,
            f"all {len(before_set)} regex preserved",
            metrics={"regex_count": len(before_set)},
        )
    removed = before_set - after_set
    added = after_set - before_set
    return GateResult(
        "G7_regex_preserved",
        GateStatus.FAIL,
        f"regex changed: {len(removed)} removed, {len(added)} added",
        metrics={"removed": list(removed)[:3], "added": list(added)[:3]},
        blocking=True,
    )


def gate_g8_recette_replay(
    cycle_id: str,
    evidence_path: Path,
    replay_fn: Callable[[Path], tuple[bool, str]] | None,
) -> GateResult:
    """G8 : Recette replay -- re-execute source, compare to saved evidence.

    replay_fn: optional callable (evidence_path) -> (ok, reason)
    """
    if replay_fn is None:
        return GateResult(
            "G8_recette_replay",
            GateStatus.SKIP,
            "no replay function provided (deferred)",
            blocking=False,
        )
    try:
        ok, reason = replay_fn(evidence_path)
        return GateResult(
            "G8_recette_replay",
            GateStatus.PASS if ok else GateStatus.FAIL,
            reason,
            blocking=True,
        )
    except Exception as e:
        return GateResult("G8_recette_replay", GateStatus.FAIL, f"replay raised: {e}")


def gate_g9_onyphe_regression(
    rule_path: Path,
    onyphe_dataset_path: Path | None,
    sample_size: int = 10,
    matcher_fn: Callable[[dict, str], bool] | None = None,
) -> GateResult:
    """G9 : Onyphe regression check on N random banners.

    Verify rule still matches expected products in ground truth.
    matcher_fn: callable (rule_data, banner_str) -> bool
                if None -> SKIP (deferred to integration tests)
    """
    if onyphe_dataset_path is None or not onyphe_dataset_path.exists():
        return GateResult(
            "G9_onyphe_regression",
            GateStatus.SKIP,
            f"dataset not available: {onyphe_dataset_path}",
            blocking=False,
        )
    if matcher_fn is None:
        return GateResult(
            "G9_onyphe_regression",
            GateStatus.SKIP,
            "matcher_fn not provided (deferred to integration tests)",
            blocking=False,
        )
    try:
        rule_data = json.loads(rule_path.read_text(encoding="utf-8"))
        product = rule_data.get("product", "").lower()
        if not product:
            return GateResult("G9_onyphe_regression", GateStatus.SKIP, "no product field")

        matching_banners: list[str] = []
        with onyphe_dataset_path.open() as fp:
            for line in fp:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                gt_product = entry.get("ground_truth", {}).get("product", "").lower()
                if gt_product == product:
                    matching_banners.append(entry.get("banner", ""))
                    if len(matching_banners) >= sample_size * 3:
                        break

        if not matching_banners:
            return GateResult(
                "G9_onyphe_regression",
                GateStatus.SKIP,
                f"no banners for product '{product}'",
                blocking=False,
            )

        sample = random.sample(matching_banners, min(sample_size, len(matching_banners)))
        matched = sum(1 for b in sample if matcher_fn(rule_data, b))
        rate = matched / len(sample)
        if rate >= 0.5:
            return GateResult(
                "G9_onyphe_regression",
                GateStatus.PASS,
                f"{matched}/{len(sample)} banners matched",
                metrics={"sample_size": len(sample), "match_rate": rate},
            )
        return GateResult(
            "G9_onyphe_regression",
            GateStatus.FAIL,
            f"detection regression: {matched}/{len(sample)} matched (<50%)",
            metrics={"sample_size": len(sample), "match_rate": rate},
            blocking=True,
        )
    except Exception as e:
        return GateResult("G9_onyphe_regression", GateStatus.FAIL, f"raised: {e}")


def gate_g10_score_no_regression(
    score_before: float | None,
    score_after: float | None,
) -> GateResult:
    """G10 : Transformative score must not regress."""
    if score_before is None:
        return GateResult(
            "G10_score_no_regression",
            GateStatus.PASS,
            "first enrich (no prior score)",
            metrics={"score_after": score_after},
        )
    if score_after is None:
        return GateResult("G10_score_no_regression", GateStatus.SKIP, "score_after not computed")
    if score_after >= score_before:
        return GateResult(
            "G10_score_no_regression",
            GateStatus.PASS,
            f"score: {score_before:.1f} -> {score_after:.1f}",
            metrics={"delta": score_after - score_before},
        )
    return GateResult(
        "G10_score_no_regression",
        GateStatus.FAIL,
        f"score regression: {score_before:.1f} -> {score_after:.1f}",
        metrics={"delta": score_after - score_before},
        blocking=True,
    )


# ======================================================================
# END gates (G11-G13) -- non-blocking
# ======================================================================

def gate_g11_decision_log_appended(journal_path: Path, action: str) -> GateResult:
    """G11 : Decision logged to journal (non-blocking)."""
    if not journal_path.exists():
        return GateResult(
            "G11_decision_log",
            GateStatus.FAIL,
            "journal missing",
            blocking=False,
        )
    try:
        last = journal_path.read_text(encoding="utf-8").strip().split("\n")[-1]
        entry = json.loads(last)
        if action in entry.get("action", ""):
            return GateResult("G11_decision_log", GateStatus.PASS, "logged", blocking=False)
        return GateResult(
            "G11_decision_log",
            GateStatus.FAIL,
            f"last entry action != {action}",
            blocking=False,
        )
    except (OSError, json.JSONDecodeError):
        return GateResult("G11_decision_log", GateStatus.FAIL, "journal unreadable", blocking=False)


def gate_g12_state_updated(state_before: dict, state_after: dict, cycle_id: str) -> GateResult:
    """G12 : State file reflects cycle completion (non-blocking)."""
    cur = state_after.get("cycles", {}).get(cycle_id, {}).get("status")
    if cur == "completed":
        return GateResult("G12_state_updated", GateStatus.PASS,
                          f"{cycle_id} marked completed", blocking=False)
    return GateResult(
        "G12_state_updated",
        GateStatus.FAIL,
        f"{cycle_id} status: {cur}",
        blocking=False,
    )


def gate_g13_metrics_recorded(state: dict) -> GateResult:
    """G13 : Transformative score history populated (non-blocking)."""
    history = state.get("transformative_score", {}).get("history", [])
    return GateResult(
        "G13_metrics_recorded",
        GateStatus.PASS if history else GateStatus.SKIP,
        f"{len(history)} score events",
        blocking=False,
    )


# ======================================================================
# STOP gates (G14-G17) -- loop termination
# ======================================================================

class StopVerdict(enum.Enum):
    CONTINUE = "CONTINUE"
    STOP_SUCCESS = "STOP_SUCCESS"      # G14
    STOP_COMPLETE = "STOP_COMPLETE"    # G15
    STOP_BUDGET = "STOP_BUDGET"        # G16
    STOP_REPLAN = "STOP_REPLAN"        # G17


def gate_g14_score_target(score: float | None, target: float) -> GateResult:
    """G14 : score >= target -> STOP_SUCCESS."""
    if score is not None and score >= target:
        return GateResult(
            "G14_score_target",
            GateStatus.PASS,
            f"score {score:.1f} >= target {target}",
            metrics={"score": score, "target": target},
        )
    return GateResult(
        "G14_score_target",
        GateStatus.SKIP,
        f"score {score} < target {target}" if score else "no score yet",
    )


def gate_g15_all_cycles_done(state: dict) -> GateResult:
    """G15 : all cycles status in {completed, skipped} -> STOP_COMPLETE."""
    cycles = state.get("cycles", {})
    for c in CYCLES:
        status = cycles.get(c, {}).get("status", "pending")
        if status not in ("completed", "skipped"):
            return GateResult(
                "G15_all_cycles_done",
                GateStatus.SKIP,
                f"{c} still {status}",
            )
    return GateResult(
        "G15_all_cycles_done",
        GateStatus.PASS,
        "all 9 cycles in completed/skipped",
    )


def gate_g16_budget_exhausted(iter_count: int, max_iter: int) -> GateResult:
    """G16 : iter_count >= max_iter -> STOP_BUDGET."""
    if iter_count >= max_iter:
        return GateResult(
            "G16_budget_exhausted",
            GateStatus.PASS,
            f"iter {iter_count} >= max {max_iter}",
            metrics={"iter_count": iter_count, "max_iter": max_iter},
        )
    return GateResult("G16_budget_exhausted", GateStatus.SKIP, f"iter {iter_count}/{max_iter}")


def gate_g17_consecutive_failures(
    consecutive_failures: int,
    threshold: int = 2,
) -> GateResult:
    """G17 : consecutive failures >= threshold -> STOP_REPLAN."""
    if consecutive_failures >= threshold:
        return GateResult(
            "G17_consecutive_failures",
            GateStatus.PASS,
            f"{consecutive_failures} consecutive failures (threshold {threshold})",
            metrics={"failures": consecutive_failures, "threshold": threshold},
        )
    return GateResult(
        "G17_consecutive_failures",
        GateStatus.SKIP,
        f"{consecutive_failures}/{threshold} failures",
    )


# ======================================================================
# Gate Engine (orchestrator)
# ======================================================================

class GateEngine:
    """Orchestrate gate execution at OODA loop checkpoints."""

    def __init__(
        self,
        rule_path: Path,
        state_manager: StateManager,
        evidence_writer: EvidenceWriter,
        onyphe_dataset_path: Path | None = None,
    ):
        self.rule_path = Path(rule_path)
        self.sm = state_manager
        self.ew = evidence_writer
        self.onyphe_dataset_path = onyphe_dataset_path
        self.history: list[GateResult] = []

    def _record(self, results: list[GateResult]) -> None:
        self.history.extend(results)

    def run_pre_act(
        self,
        cycle_id: str,
        rule_data: dict,
        lock: LockManager | None,
        dep_check: Callable[[], tuple[bool, str]] | None = None,
    ) -> list[GateResult]:
        state = self.sm.load(self.rule_path)
        results = [
            gate_g1_lock_acquired(lock),
            gate_g2_rule_schema_valid(rule_data),
            gate_g3_dependency_available(cycle_id, dep_check),
            gate_g4_state_coherent(self.rule_path, state),
        ]
        self._record(results)
        return results

    def run_post_act(
        self,
        cycle_id: str,
        rule_before: dict,
        rule_after: dict,
        evidence_path: Path,
        score_before: float | None = None,
        score_after: float | None = None,
        replay_fn: Callable[[Path], tuple[bool, str]] | None = None,
        matcher_fn: Callable[[dict, str], bool] | None = None,
    ) -> list[GateResult]:
        results = [
            gate_g5_evidence_sha256(evidence_path, self.ew),
            gate_g6_atomic_rule_write(self.rule_path),
            gate_g7_regex_preserved(rule_before, rule_after),
            gate_g8_recette_replay(cycle_id, evidence_path, replay_fn),
            gate_g9_onyphe_regression(self.rule_path, self.onyphe_dataset_path, matcher_fn=matcher_fn),
            gate_g10_score_no_regression(score_before, score_after),
        ]
        self._record(results)
        return results

    def run_end(
        self,
        cycle_id: str,
        state_before: dict,
        state_after: dict,
        journal_path: Path | None = None,
        action: str = "CYCLE_OK",
    ) -> list[GateResult]:
        """END gates G11-G13 (non-blocking, observability only).

        Run after a successful cycle to validate that traceability artifacts
        are properly written :
        - G11 : decision_log entry was appended for this action
        - G12 : state file reflects cycle completion
        - G13 : transformative_score history was updated

        All gates are non-blocking. Failures only log warnings.
        """
        results: list[GateResult] = []
        if journal_path is not None:
            results.append(gate_g11_decision_log_appended(journal_path, action))
        else:
            results.append(GateResult(
                "G11_decision_log",
                GateStatus.SKIP,
                "no journal_path provided",
                blocking=False,
            ))
        results.append(gate_g12_state_updated(state_before, state_after, cycle_id))
        results.append(gate_g13_metrics_recorded(state_after))
        self._record(results)
        return results

    def run_stop(
        self,
        score: float | None,
        target: float,
        iter_count: int,
        max_iter: int,
        consecutive_failures: int,
    ) -> tuple[StopVerdict, list[GateResult]]:
        state = self.sm.load(self.rule_path)
        gates = [
            gate_g14_score_target(score, target),
            gate_g15_all_cycles_done(state),
            gate_g16_budget_exhausted(iter_count, max_iter),
            gate_g17_consecutive_failures(consecutive_failures),
        ]
        self._record(gates)
        # First PASS dictates verdict
        for g in gates:
            if g.is_pass():
                if g.gate_id.startswith("G14"):
                    return StopVerdict.STOP_SUCCESS, gates
                if g.gate_id.startswith("G15"):
                    return StopVerdict.STOP_COMPLETE, gates
                if g.gate_id.startswith("G16"):
                    return StopVerdict.STOP_BUDGET, gates
                if g.gate_id.startswith("G17"):
                    return StopVerdict.STOP_REPLAN, gates
        return StopVerdict.CONTINUE, gates

    @staticmethod
    def all_pass(results: list[GateResult]) -> bool:
        return all(r.is_pass() or r.status == GateStatus.SKIP for r in results)

    @staticmethod
    def any_blocking_fail(results: list[GateResult]) -> bool:
        return any(r.is_fail() and r.blocking for r in results)


__all__ = [
    "GateStatus",
    "GateResult",
    "GateEngine",
    "StopVerdict",
    # Individual gates (testable)
    "gate_g1_lock_acquired",
    "gate_g2_rule_schema_valid",
    "gate_g3_dependency_available",
    "gate_g4_state_coherent",
    "gate_g5_evidence_sha256",
    "gate_g6_atomic_rule_write",
    "gate_g7_regex_preserved",
    "gate_g8_recette_replay",
    "gate_g9_onyphe_regression",
    "gate_g10_score_no_regression",
    "gate_g11_decision_log_appended",
    "gate_g12_state_updated",
    "gate_g13_metrics_recorded",
    "gate_g14_score_target",
    "gate_g15_all_cycles_done",
    "gate_g16_budget_exhausted",
    "gate_g17_consecutive_failures",
]
