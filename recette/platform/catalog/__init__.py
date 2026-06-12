"""Catalog registry: aggregates the 11 domain modules into one lookup table."""

from __future__ import annotations

import importlib

from .domains import DOMAIN_MODULES
from .model import ActionSpec, RiskLevel  # noqa: F401  (re-export)


class CatalogError(ValueError):
    """Raised when domain modules collide or are malformed."""


class Catalog:
    def __init__(self, specs: tuple[ActionSpec, ...]) -> None:
        self._by_key: dict[tuple[str, str], ActionSpec] = {}
        for spec in specs:
            key = (spec.target_system, spec.action_type)
            if key in self._by_key:
                raise CatalogError(f"duplicate action {key!r}")
            self._by_key[key] = spec
        self._specs = specs

    def get(self, target_system: str, action_type: str) -> ActionSpec | None:
        return self._by_key.get((target_system, action_type))

    def all(self) -> tuple[ActionSpec, ...]:
        return self._specs

    def target_systems(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for spec in self._specs:
            seen.setdefault(spec.target_system, None)
        return tuple(seen)

    def __len__(self) -> int:
        return len(self._specs)


def load_catalog() -> Catalog:
    """Import every registered domain module and aggregate its ACTIONS."""
    specs: list[ActionSpec] = []
    for name in DOMAIN_MODULES:
        module = importlib.import_module(f"{__name__}.domains.{name}")
        target = getattr(module, "TARGET_SYSTEM", None)
        actions = getattr(module, "ACTIONS", None)
        if not isinstance(target, str) or not isinstance(actions, tuple):
            raise CatalogError(f"domain module {name!r} must export TARGET_SYSTEM and ACTIONS")
        for spec in actions:
            if spec.target_system != target:
                raise CatalogError(
                    f"spec {spec.action_type!r} in module {name!r} declares "
                    f"target_system {spec.target_system!r}, expected {target!r}"
                )
            specs.append(spec)
    return Catalog(tuple(specs))
