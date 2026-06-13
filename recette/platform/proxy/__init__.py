"""Data Plane proxies (I5): the ONLY path to external systems."""

from .lab_proxy import LabHttpProxy
from .protocol import ExecutionResult, ExternalSystemProxy, side_effect_hash
from .real_proxy import RealForgeProxy, build_real_proxy_factory
from .router import resolve_proxy
from .tracing import (
    ProxyTrace,
    RingTraceRecorder,
    TraceRecorder,
    TracingProxy,
    debug_enabled_from_env,
)

__all__ = [
    "ExecutionResult",
    "ExternalSystemProxy",
    "LabHttpProxy",
    "ProxyTrace",
    "RealForgeProxy",
    "RingTraceRecorder",
    "TraceRecorder",
    "TracingProxy",
    "build_real_proxy_factory",
    "debug_enabled_from_env",
    "resolve_proxy",
    "side_effect_hash",
]
