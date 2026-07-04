"""Bridge the Rust ``AgentInventory`` JSON into Python ``DiscoveryRisk`` objects.

The ``discoveryprobe-inventory`` CLI emits an ``AgentInventory`` report (see
``discoveryprobe/discoveryprobe-inventory/src/model.rs``): a kind-tagged JSON
document (Task 5) where every enum value is an object with a ``"kind"`` key, so
this bridge dispatches on ``value["kind"]`` without shape guessing. The bridge
is a BOUNDARY: malformed input raises a clear ``ValueError`` with context, never
a silent empty list (fail-safe -- a broken inventory must be loud, not dropped).

Design choices (documented, per Task 13):

- Return type is ``BridgedInventory``, NOT a bare ``list[DiscoveryRisk]``. A
  ``DiscoveryRisk`` has no home for violations or comm edges, so returning
  ``{risks, violations, undeclared_edges}`` keeps ``DiscoveryRisk`` unchanged
  while still surfacing the passport violations and undeclared handoff edges the
  console/harness must show. This is the faithful choice sanctioned by the task.

- ``passport_status`` comes straight from ``passport.kind`` ("present" /
  "absent" / "invalid"), the single source of truth the Rust scanner already
  emits (never re-derived here).

- ``canonical_agent_id`` mirrors the Python reference adapter
  (``ReferenceSourceScanAdapter._build_risks``): ``sha256(principal)[:16]``. The
  principal is the declared principal when a valid passport exists, else the
  record ``agent_id`` (a shadow/invalid record has no declared principal). This
  keeps bridge output comparable to the reference adapter for a present agent.

- ``action_pattern``: one ``DiscoveryRisk`` per ``declared.actions`` when a
  passport declares actions; otherwise the observed actions; when neither exists
  (absent/invalid records carry no declaration and, statically, no observation)
  a single risk with the sentinel ``"unknown"`` -- so the ``passport_status``
  and violations still surface even when the action set is unknowable.

- ``target_system``: ``declared.target_systems[0]`` when declared, else the
  sentinel ``"unknown"`` (a declaration-less record has no target).

- ``estimated_risk``: this bridge does NOT re-derive the Python level heuristic
  (action set + CI permissions); that lives in the reference adapter. It carries
  a minimal, documented signal instead: ``level`` is 3 when the record has
  violations (a shadow / violating agent is high concern) else 0. The bridge is
  about passport_status + violation fidelity, not re-deriving the risk level.

Determinism (I4): the Rust inventory is already sorted (agents by ``agent_id``,
violations by their derived order, edges by ``(from, to)``); this bridge
preserves that order and adds no clock/random, so the same input yields byte-
stable output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from recette.adapters import DiscoveryRisk

#: Sentinel action / target for a record that declares neither (absent/invalid).
_UNKNOWN = "unknown"


@dataclass(frozen=True)
class BridgedInventory:
    """Parsed ``AgentInventory``: the discovery risks plus the violations and
    undeclared communication edges that have no home on ``DiscoveryRisk``."""

    #: One risk per declared (or observed) action, in inventory order.
    risks: list[DiscoveryRisk] = field(default_factory=list)
    #: Every violation, each carrying its ``agent_id`` plus the Rust
    #: kind-tagged violation fields (``kind`` + payload), in inventory order.
    violations: list[dict] = field(default_factory=list)
    #: Observed edges absent from the declared graph (``{from, to}``), sorted.
    undeclared_edges: list[dict] = field(default_factory=list)


def _canonical_agent_id(principal: str) -> str:
    """Stable id mirroring the reference adapter: ``sha256(principal)[:16]``."""
    return hashlib.sha256(principal.encode("utf-8")).hexdigest()[:16]


def _record_violations(record: dict) -> list[dict]:
    """Extract the kind-tagged violations of one record, if any.

    ``conformity`` is kind-tagged: only ``{"kind": "violations", ...}`` carries a
    ``violations`` list; ``conform`` and ``not_observed`` carry none.
    """
    conformity = record.get("conformity")
    if not isinstance(conformity, dict):
        raise ValueError(f"agent record has no kind-tagged conformity: {record.get('agent_id')!r}")
    if conformity.get("kind") != "violations":
        return []
    raw_violations = conformity.get("violations")
    if not isinstance(raw_violations, list):
        raise ValueError(f"violations conformity missing its list: {record.get('agent_id')!r}")
    return list(raw_violations)


def _record_actions(declared: dict | None, observed: dict) -> list[str]:
    """Action set for a record: declared actions, else observed, else sentinel."""
    if declared is not None:
        actions = declared.get("actions") or []
        if actions:
            return list(actions)
    observed_actions = observed.get("actions") or []
    if observed_actions:
        return list(observed_actions)
    return [_UNKNOWN]


def _record_target(declared: dict | None) -> str:
    """First declared target system, or the sentinel for a declaration-less record."""
    if declared is not None:
        targets = declared.get("target_systems") or []
        if targets:
            return str(targets[0])
    return _UNKNOWN


def _record_risks(record: dict, has_violations: bool) -> list[DiscoveryRisk]:
    """Map one agent record to one ``DiscoveryRisk`` per action."""
    passport = record.get("passport")
    if not isinstance(passport, dict) or "kind" not in passport:
        raise ValueError(f"agent record has no kind-tagged passport: {record.get('agent_id')!r}")
    passport_status = str(passport["kind"])

    declared = record.get("declared")
    if declared is not None and not isinstance(declared, dict):
        raise ValueError(f"agent record 'declared' is not an object: {record.get('agent_id')!r}")
    observed = record.get("observed") or {}

    principal = declared["principal"] if declared else str(record.get("agent_id", ""))
    canonical = _canonical_agent_id(principal)
    target = _record_target(declared)
    level = 3 if has_violations else 0

    return [
        DiscoveryRisk(
            canonical_agent_id=canonical,
            action_pattern=action,
            target_system=target,
            estimated_risk={"level": level},
            passport_status=passport_status,
        )
        for action in _record_actions(declared, observed)
    ]


def parse_inventory(raw: str) -> BridgedInventory:
    """Parse an ``AgentInventory`` JSON document into a ``BridgedInventory``.

    Raises ``ValueError`` (with context) on malformed JSON or a shape that does
    not match the inventory contract -- a boundary error is correct, never a
    silent empty result.
    """
    try:
        inventory = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"inventory is not valid JSON: {exc}") from exc
    if not isinstance(inventory, dict):
        raise ValueError("inventory JSON is not an object")

    agents = inventory.get("agents")
    if not isinstance(agents, list):
        raise ValueError("inventory has no 'agents' list")

    risks: list[DiscoveryRisk] = []
    violations: list[dict] = []
    for record in agents:
        if not isinstance(record, dict):
            raise ValueError("inventory 'agents' entry is not an object")
        record_violations = _record_violations(record)
        agent_id = str(record.get("agent_id", ""))
        for violation in record_violations:
            if not isinstance(violation, dict):
                raise ValueError(f"violation of {agent_id!r} is not an object")
            violations.append({"agent_id": agent_id, **violation})
        risks.extend(_record_risks(record, has_violations=bool(record_violations)))

    comm_graph = inventory.get("comm_graph") or {}
    if not isinstance(comm_graph, dict):
        raise ValueError("inventory 'comm_graph' is not an object")
    raw_undeclared = comm_graph.get("undeclared_edges") or []
    if not isinstance(raw_undeclared, list):
        raise ValueError("inventory 'undeclared_edges' is not a list")
    undeclared_edges = [dict(edge) for edge in raw_undeclared if isinstance(edge, dict)]

    return BridgedInventory(
        risks=risks,
        violations=violations,
        undeclared_edges=undeclared_edges,
    )
