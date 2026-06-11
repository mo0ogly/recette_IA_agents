"""
ooda_engine -- OODA loop orchestrator for liaprobe rule enrichment.

OBSERVE -> ORIENT -> DECIDE -> ACT -> (gate) -> loop.

Stop conditions (G14-G17):
- Score >= target  -> STOP_SUCCESS
- All cycles done  -> STOP_COMPLETE
- Max iter reached -> STOP_BUDGET
- 2+ failures      -> STOP_REPLAN

See OODA_DESIGN.md for full design.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Callable

from enrich_lib import (
    CYCLES,
    AtomicJSONWriter,
    DependencyMissingError,
    EnrichError,
    EvidenceWriter,
    InvalidInputError,
    LockManager,
    StateManager,
    StructuredLogger,
    sha256_file,
    utc_now_iso,
)
from quality_gate import GateEngine, GateStatus, StopVerdict


# ======================================================================
# Decision engine -- priorisation
# ======================================================================

CYCLE_PRIORITIES = {
    # Higher = run first
    "cycle_4_cve":           60,  # high impact, AUTO
    "cycle_5_eol":           40,  # medium, AUTO
    "cycle_7_mitre":         50,  # depends on cycle 4
    "cycle_6_compliance":    20,  # manual, low priority
    "cycle_8_default_creds": 30,  # AUTO -- file-based master, 35 products covered
    "cycle_9_cert_patterns": 25,  # AUTO -- TLS X.509 patterns sourced from vendor docs
    "cycle_10_behavior":     20,
    "cycle_11_cluster_tls":  10,
    "cycle_12_honeypot":     10,
}


@dataclasses.dataclass
class Decision:
    action: str                         # "RUN_CYCLE" / "STOP" / "ESCALATE"
    cycle_id: str | None = None
    reason: str = ""
    priority: int = 0


def decide_next_action(state: dict, score: float | None, target: float) -> Decision:
    """Pick next cycle to run, or decide to stop.

    Priority order:
    1. Pending cycles with dependencies satisfied, by CYCLE_PRIORITIES desc
    2. STOP if score reached target
    3. STOP if all cycles done
    """
    cycles = state.get("cycles", {})

    # Check stops first
    if score is not None and score >= target:
        return Decision("STOP", reason=f"score {score:.1f} >= target {target}")

    pending: list[tuple[str, int]] = []
    for c, prio in CYCLE_PRIORITIES.items():
        status = cycles.get(c, {}).get("status", "pending")
        if status == "pending":
            # Cycle 7 depends on cycle 4 (CVE list)
            if c == "cycle_7_mitre":
                cve_status = cycles.get("cycle_4_cve", {}).get("status")
                if cve_status not in ("completed", "skipped"):
                    continue  # cycle 4 not yet done
            pending.append((c, prio))

    if not pending:
        return Decision("STOP", reason="all cycles done or skipped")

    pending.sort(key=lambda t: -t[1])
    cycle_id, prio = pending[0]
    return Decision("RUN_CYCLE", cycle_id=cycle_id, priority=prio,
                    reason=f"priority {prio} (highest pending)")


# ======================================================================
# Transformative score (simplified MVP)
# ======================================================================

# Section weights -- see SCORING.md
SECTION_WEIGHTS = {
    "known_cves": 25,
    "lifecycle": 15,
    "attack_surface": 20,
    "compliance": 15,
    "default_credentials": 10,
    "common_misconfigs": 5,
    "behavior": 5,
    "plugins": 3,
    "cluster_topology": 1,
    "tls_signals": 1,
}


def compute_transformative_score(rule_data: dict) -> float:
    """Weighted score 0-100 based on enrichment sections present.

    100 = all sections populated.
    """
    total = 0.0
    for section, weight in SECTION_WEIGHTS.items():
        v = rule_data.get(section)
        if v is None:
            continue
        if isinstance(v, list) and len(v) > 0:
            total += weight
        elif isinstance(v, dict) and len(v) > 0:
            total += weight
    return round(total, 1)


# ======================================================================
# Cycle registry -- maps cycle_id to executable callable
# ======================================================================

# A cycle handler signature:
#   handler(rule_path: Path, rule_data: dict, ew: EvidenceWriter,
#           sm: StateManager, lock: LockManager) -> tuple[bool, dict, dict]
# Returns: (success, applied_diff, summary)
CycleHandler = Callable[
    [Path, dict, EvidenceWriter, StateManager, LockManager],
    tuple[bool, dict, dict],
]


# ======================================================================
# OODA Engine
# ======================================================================

@dataclasses.dataclass
class OODAResult:
    rule_path: Path
    iterations: int
    cycles_completed: list[str]
    cycles_skipped: list[str]
    cycles_failed: list[str]
    final_score: float
    verdict: StopVerdict
    consecutive_failures: int = 0


class OODAEngine:
    """Run OODA loop until stop condition.

    Args:
        rule_path: Path to fingerprint rule.json
        state_manager: shared StateManager
        evidence_writer: shared EvidenceWriter
        cycle_handlers: dict {cycle_id: CycleHandler}
        target_score: stop when transformative_score >= target (default 70)
        max_iter: stop after N iterations (default 12)
        onyphe_dataset_path: optional path to Onyphe dataset for G9
        journal: StructuredLogger for audit trail
    """

    def __init__(
        self,
        rule_path: Path,
        state_manager: StateManager,
        evidence_writer: EvidenceWriter,
        cycle_handlers: dict[str, CycleHandler],
        target_score: float = 70.0,
        max_iter: int = 12,
        onyphe_dataset_path: Path | None = None,
        journal: StructuredLogger | None = None,
    ):
        self.rule_path = Path(rule_path)
        self.sm = state_manager
        self.ew = evidence_writer
        self.cycle_handlers = cycle_handlers
        self.target_score = target_score
        self.max_iter = max_iter
        self.onyphe_dataset_path = onyphe_dataset_path
        self.journal = journal
        self.gate_engine = GateEngine(
            rule_path=self.rule_path,
            state_manager=state_manager,
            evidence_writer=evidence_writer,
            onyphe_dataset_path=onyphe_dataset_path,
        )

    def _read_rule(self) -> dict:
        return json.loads(self.rule_path.read_text(encoding="utf-8"))

    def _log(self, **fields: Any) -> None:
        if self.journal is not None:
            self.journal.log(rule=str(self.rule_path), **fields)

    def run(self) -> OODAResult:
        cycles_completed: list[str] = []
        cycles_skipped: list[str] = []
        cycles_failed: list[str] = []
        consecutive_failures = 0
        iter_count = 0

        for iter_count in range(1, self.max_iter + 1):
            # OBSERVE
            state = self.sm.load(self.rule_path)
            rule_data = self._read_rule()
            score = compute_transformative_score(rule_data)
            self._log(action="OBSERVE", iter=iter_count, score=score,
                      lifecycle=state.get("lifecycle_state"))

            # STOP gates evaluated first
            verdict, _ = self.gate_engine.run_stop(
                score=score,
                target=self.target_score,
                iter_count=iter_count - 1,
                max_iter=self.max_iter,
                consecutive_failures=consecutive_failures,
            )
            if verdict != StopVerdict.CONTINUE:
                self._log(action="STOP", verdict=verdict.value, iter=iter_count)
                return OODAResult(
                    self.rule_path, iter_count - 1,
                    cycles_completed, cycles_skipped, cycles_failed,
                    score, verdict, consecutive_failures,
                )

            # ORIENT + DECIDE
            decision = decide_next_action(state, score, self.target_score)
            self._log(action="DECIDE", decision=decision.action,
                      cycle=decision.cycle_id, reason=decision.reason)

            if decision.action == "STOP":
                # Re-run stop gates
                verdict, _ = self.gate_engine.run_stop(
                    score, self.target_score, iter_count,
                    self.max_iter, consecutive_failures,
                )
                if verdict == StopVerdict.CONTINUE:
                    verdict = StopVerdict.STOP_COMPLETE
                return OODAResult(
                    self.rule_path, iter_count,
                    cycles_completed, cycles_skipped, cycles_failed,
                    score, verdict, consecutive_failures,
                )

            cycle_id = decision.cycle_id
            if cycle_id is None or cycle_id not in self.cycle_handlers:
                self._log(action="SKIP", cycle=cycle_id, reason="no handler")
                if cycle_id:
                    self.sm.mark_cycle_skipped(self.rule_path, cycle_id, "no handler registered")
                    cycles_skipped.append(cycle_id)
                continue

            # ACT (with PRE-ACT and POST-ACT gates)
            success, why = self._execute_cycle(cycle_id, rule_data, score)
            if success:
                cycles_completed.append(cycle_id)
                consecutive_failures = 0
            else:
                cycles_failed.append(cycle_id)
                consecutive_failures += 1
                self._log(action="FAILURE", cycle=cycle_id, reason=why,
                          consecutive=consecutive_failures)

        # Loop exhausted
        state = self.sm.load(self.rule_path)
        score = compute_transformative_score(self._read_rule())
        return OODAResult(
            self.rule_path, iter_count,
            cycles_completed, cycles_skipped, cycles_failed,
            score, StopVerdict.STOP_BUDGET, consecutive_failures,
        )

    def _execute_cycle(
        self,
        cycle_id: str,
        rule_before: dict,
        score_before: float,
    ) -> tuple[bool, str]:
        """Execute ACT phase with pre/post gates. Returns (success, reason)."""
        handler = self.cycle_handlers[cycle_id]
        with self.sm.lock(self.rule_path) as lock:
            # PRE-ACT gates (G1-G4)
            state_before = self.sm.load(self.rule_path)
            pre_results = self.gate_engine.run_pre_act(
                cycle_id=cycle_id,
                rule_data=rule_before,
                lock=lock,
            )
            if self.gate_engine.any_blocking_fail(pre_results):
                fails = [r for r in pre_results if r.is_fail() and r.blocking]
                reason = "; ".join(f"{r.gate_id}: {r.reason}" for r in fails)
                self._log(action="PRE_ACT_FAIL", cycle=cycle_id, reason=reason)
                return False, reason

            # Backup rule before mutation
            rule_bak = self.rule_path.with_suffix(self.rule_path.suffix + ".bak")
            rule_bak.write_text(self.rule_path.read_text(encoding="utf-8"), encoding="utf-8")

            # ACT -- invoke handler
            try:
                success, applied_diff, summary = handler(
                    self.rule_path, rule_before, self.ew, self.sm, lock,
                )
            except (
                EnrichError, DependencyMissingError, InvalidInputError,
                OSError, ValueError, KeyError, TypeError, RuntimeError,
            ) as e:
                # Narrow exceptions: KeyboardInterrupt + SystemExit propagate (R26)
                self._rollback(rule_bak)
                self._log(action="ACT_RAISED", cycle=cycle_id,
                          error_type=type(e).__name__, error=str(e))
                return False, f"handler raised {type(e).__name__}: {e}"

            if not success:
                self._rollback(rule_bak)
                self._log(action="ACT_FAILED", cycle=cycle_id)
                return False, "handler returned success=False"

            # POST-ACT gates (G5-G10)
            rule_after = self._read_rule()
            score_after = compute_transformative_score(rule_after)
            # find latest evidence
            cycle_status = self.sm.get_cycle_status(self.rule_path, cycle_id)
            evidence_path = Path(cycle_status.evidence_path) if cycle_status.evidence_path else None
            if evidence_path is None or not evidence_path.exists():
                self._rollback(rule_bak)
                return False, "evidence not written"

            post_results = self.gate_engine.run_post_act(
                cycle_id=cycle_id,
                rule_before=rule_before,
                rule_after=rule_after,
                evidence_path=evidence_path,
                score_before=score_before,
                score_after=score_after,
            )
            if self.gate_engine.any_blocking_fail(post_results):
                fails = [r for r in post_results if r.is_fail() and r.blocking]
                reason = "; ".join(f"{r.gate_id}: {r.reason}" for r in fails)
                self._rollback(rule_bak)
                self._log(action="POST_ACT_FAIL", cycle=cycle_id, reason=reason)
                return False, reason

            # Cleanup .bak (keep last successful state)
            try:
                rule_bak.unlink()
            except OSError:
                pass

            self._log(action="CYCLE_OK", cycle=cycle_id, score_after=score_after)

            # END gates (G11-G13, non-blocking observability)
            state_after = self.sm.load(self.rule_path)
            journal_path = self.journal.log_path if self.journal else None
            end_results = self.gate_engine.run_end(
                cycle_id=cycle_id,
                state_before=state_before,
                state_after=state_after,
                journal_path=journal_path,
                action="CYCLE_OK",
            )
            for r in end_results:
                if r.is_fail():
                    self._log(action="END_GATE_WARN",
                              cycle=cycle_id, gate=r.gate_id, reason=r.reason)

            return True, "OK"

    def _rollback(self, rule_bak: Path) -> None:
        """Restore rule.json from .bak."""
        if rule_bak.exists():
            try:
                self.rule_path.write_text(
                    rule_bak.read_text(encoding="utf-8"), encoding="utf-8"
                )
                rule_bak.unlink()
            except OSError as e:
                self._log(action="ROLLBACK_FAIL", error=str(e))


__all__ = [
    "Decision",
    "OODAEngine",
    "OODAResult",
    "decide_next_action",
    "compute_transformative_score",
    "CYCLE_PRIORITIES",
    "SECTION_WEIGHTS",
]
