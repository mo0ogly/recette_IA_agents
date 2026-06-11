"""Collector registry for nightly harvest."""

from .base import Collector, CollectorResult, CollectorRequest

from .netlas import NetlasCollector
from .censys import CensysCollector
from .zoomeye import ZoomEyeCollector
from .crtsh import CrtShCollector
from .publicwww import PublicWwwCollector
from .rapid7_sonar import Rapid7SonarCollector

REGISTRY: dict[str, type[Collector]] = {
    "netlas": NetlasCollector,
    "censys": CensysCollector,
    "zoomeye": ZoomEyeCollector,
    "crtsh": CrtShCollector,
    "publicwww": PublicWwwCollector,
    "rapid7_sonar": Rapid7SonarCollector,
}

__all__ = [
    "REGISTRY",
    "Collector",
    "CollectorResult",
    "CollectorRequest",
]
