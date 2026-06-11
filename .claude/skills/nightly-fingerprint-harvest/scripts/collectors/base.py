"""Collector interface contract.

Each external source implements one Collector subclass.
The orchestrator calls .search(request) -> list[CollectorResult].

Collectors NEVER raise on quota/auth failure. They return an empty list
and surface the error string via CollectorResult.error so the orchestrator
can log it without aborting the whole nightly run.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CollectorRequest:
    rule_id: str
    vendor: str
    product: str
    taxonomy_code: str
    query_seed: str = ""
    literal_needles: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    max_hosts: int = 5
    extra_hints: dict = field(default_factory=dict)


@dataclass
class CollectorResult:
    source: str
    host: str
    port: int = 0
    capture_url: str = ""
    http_status: int = 0
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    banner: Optional[str] = None
    latency_ms: int = 0
    raw_record: dict = field(default_factory=dict)
    error: Optional[str] = None


class Collector(ABC):
    name: str = "base"
    requires_auth: bool = False
    auth_env_keys: tuple[str, ...] = ()

    def is_configured(self) -> bool:
        import os
        if not self.requires_auth:
            return True
        return all(os.environ.get(k) for k in self.auth_env_keys)

    @abstractmethod
    def search(self, request: CollectorRequest) -> list[CollectorResult]:
        """Search for hosts matching the rule + capture evidence."""
