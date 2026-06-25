"""Lens registry -- each lens is a pure ``(AgentContext, AnalysisProfile) ->
list[Finding]``.

A lens looks at ONE agent's annotated wire + declared plan and emits findings. The
profile decides whether a lens runs (``profile.lenses``) and at what severity
(``profile.threshold(lens)``; ``"off"`` mutes it). Lenses are deliberately small
and independent so a researcher can enable/disable them and measure each one's
contribution (ablation). The two *behavioral* lenses -- ``sequence`` (temporal:
order of events) and ``baseline`` (novelty vs a frozen fingerprint) -- are what
make this more than a set of static detectors.

Standards tags (R23) map each finding to OWASP Top 10 for Agentic Apps 2026 +
MITRE ATLAS, verified against the canonical mapping in
``.claude/rules/redteam-standards-alignment.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..surface.agent_analysis import _doh_host, _is_credential_path
from .profile import AnalysisProfile
from .report import Finding


@dataclass(frozen=True)
class AgentContext:
    """The per-agent input a lens reads. ``annotations`` is the ORDERED list of
    ``netmap.annotate_token`` dicts (order preserved for the sequence lens)."""

    agent_id: str
    annotations: list[dict]
    declared: dict = field(default_factory=dict)
    baseline: dict | None = None

    # --- derived views (computed once, pure) ---
    def dialed(self) -> list[str]:
        return [
            str(a["name"]) for a in self.annotations if a.get("kind") == "connect" and a.get("name")
        ]

    def undeclared_egress(self) -> list[str]:
        return [
            a["raw"][len("connect:") :]
            for a in self.annotations
            if a.get("kind") == "connect" and a.get("undeclared")
        ]

    def undeclared_dns(self) -> list[str]:
        return [
            a["raw"][len("dns:") :]
            for a in self.annotations
            if a.get("kind") == "dns" and a.get("undeclared")
        ]

    def opens(self) -> list[str]:
        return [
            a["raw"][len("open:") :]
            for a in self.annotations
            if a.get("kind") == "open"
            for p in [a["raw"][len("open:") :]]
            if p and p != "<unknown>"
        ]


def _muted(profile: AnalysisProfile, key: str) -> bool:
    """A lens is muted when its threshold is the literal ``"off"``."""
    return profile.threshold(key) == "off"


def _sev(profile: AnalysisProfile, key: str, default: str) -> str:
    val = profile.threshold(key)
    return val if isinstance(val, str) and val in ("alert", "warn", "info") else default


def lens_egress(ctx: AgentContext, profile: AnalysisProfile) -> list[Finding]:
    """Undeclared egress (non-resolver hosts) = possible exfiltration. Honors
    ``ghost_host_tolerance`` (tolerate up to N undeclared hosts before flagging)."""
    if _muted(profile, "egress"):
        return []
    hosts = sorted({h for h in ctx.undeclared_egress() if _doh_host(h) is None})
    tolerance = profile.threshold("ghost_host_tolerance")
    tol = tolerance if isinstance(tolerance, int) and not isinstance(tolerance, bool) else 0
    if len(hosts) <= tol:
        return []
    sev = _sev(profile, "egress", "alert")
    return [
        Finding(
            "egress",
            sev,
            f"egress connect to UNDECLARED host {h}",
            "possible exfiltration -- not in the server registry",
            owasp_asi="ASI02",
            mitre_atlas="AML.T0086",
        )
        for h in hosts
    ]


def lens_doh(ctx: AgentContext, profile: AnalysisProfile) -> list[Finding]:
    """Undeclared egress to a public DNS resolver on :443 = DNS-over-HTTPS tunnel."""
    if _muted(profile, "doh"):
        return []
    resolvers = sorted({h for ep in ctx.undeclared_egress() if (h := _doh_host(ep))})
    sev = _sev(profile, "doh", "alert")
    return [
        Finding(
            "doh",
            sev,
            f"egress to public DNS resolver {h}:443",
            "DNS-over-HTTPS covert channel -- tunneling exfil past a port-53 allow-list",
            owasp_asi="ASI02",
            mitre_atlas="AML.T0086",
        )
        for h in resolvers
    ]


def lens_dns(ctx: AgentContext, profile: AnalysisProfile) -> list[Finding]:
    """A DNS query for an undeclared name = DNS exfil/tunneling tripwire."""
    if _muted(profile, "dns"):
        return []
    names = sorted(set(ctx.undeclared_dns()))
    sev = _sev(profile, "dns", "alert")
    return [
        Finding(
            "dns",
            sev,
            f"DNS query for UNDECLARED name {n}",
            "possible DNS exfil/tunneling -- outside declared fqdns",
            owasp_asi="ASI02",
            mitre_atlas="AML.T0086",
        )
        for n in names
    ]


def lens_credential(ctx: AgentContext, profile: AnalysisProfile) -> list[Finding]:
    """Access to secret-material files = exfil-prep (never routine I/O here)."""
    if _muted(profile, "credential"):
        return []
    creds = sorted({p for p in ctx.opens() if _is_credential_path(p)})
    sev = _sev(profile, "credential", "alert")
    return [
        Finding(
            "credential",
            sev,
            f"credential/secret file access {p}",
            "secret-material read -- exfil-prep, never routine I/O",
            owasp_asi="ASI03",
            mitre_atlas="AML.T0055",
        )
        for p in creds
    ]


def lens_process(ctx: AgentContext, profile: AnalysisProfile) -> list[Finding]:
    """Child-process lifecycle (fork/exec) = a spawned helper to attribute."""
    if _muted(profile, "process"):
        return []
    if not any(a.get("kind") in ("fork", "exec") for a in ctx.annotations):
        return []
    sev = _sev(profile, "process", "info")
    return [
        Finding(
            "process",
            sev,
            "child process lifecycle (fork/exec)",
            "capture the child pid tree so a spawned helper is attributed to this agent",
            owasp_asi="ASI05",
            mitre_atlas="AML.T0053",
        )
    ]


def lens_said_scope(ctx: AgentContext, profile: AnalysisProfile) -> list[Finding]:
    """A decided action outside the declared capability_scope = capability drift.
    ``scope=lax`` only flags it when the agent ALSO dialed an out-of-plan server."""
    if _muted(profile, "said_scope"):
        return []
    decided = ctx.declared.get("decided")
    if decided is None:
        return []
    scope = set(ctx.declared.get("scope", []) or [])
    out = sorted(a for a in decided if a not in scope)
    if not out:
        return []
    if profile.threshold("scope") == "lax":
        systems = set(ctx.declared.get("systems", []) or [])
        if all(s in systems for s in ctx.dialed()):
            return []
    sev = _sev(profile, "said_scope", "warn")
    return [
        Finding(
            "said_scope",
            sev,
            f"decided action {a} OUTSIDE declared capability_scope",
            "the agent said it would do more than it declared",
            owasp_asi="ASI02",
            mitre_atlas="AML.T0053",
        )
        for a in out
    ]


def lens_sequence(ctx: AgentContext, profile: AnalysisProfile) -> list[Finding]:
    """Behavioral (temporal): the ORDER of events. Detects the exfil chain
    'read a credential, THEN reach an undeclared host' -- a pattern a set-based
    detector misses because each event alone may look benign."""
    if _muted(profile, "sequence"):
        return []
    first_credential: int | None = None
    findings: list[Finding] = []
    for idx, a in enumerate(ctx.annotations):
        kind = a.get("kind")
        if kind == "open":
            path = a["raw"][len("open:") :]
            if first_credential is None and _is_credential_path(path):
                first_credential = idx
        elif kind == "connect" and a.get("undeclared") and first_credential is not None:
            host = a["raw"][len("connect:") :]
            findings.append(
                Finding(
                    "sequence",
                    _sev(profile, "sequence", "alert"),
                    f"exfil chain: credential read then egress to {host}",
                    "a secret was read BEFORE an undeclared egress -- ordered exfil, "
                    "not two unrelated events",
                    owasp_asi="ASI02",
                    mitre_atlas="AML.T0086",
                )
            )
            break
    return findings


def lens_baseline(ctx: AgentContext, profile: AnalysisProfile) -> list[Finding]:
    """Behavioral (novelty): deviation from a frozen per-agent baseline -- a dialed
    server the baseline never saw, or a connect count above its ceiling. Skipped
    when no baseline is provided (the lens is a no-op, not a false positive)."""
    if _muted(profile, "baseline") or not ctx.baseline:
        return []
    known = set(ctx.baseline.get("servers", []) or [])
    novel = sorted({s for s in ctx.dialed() if s and s not in known})
    findings: list[Finding] = []
    sev = _sev(profile, "baseline", "warn")
    for srv in novel:
        findings.append(
            Finding(
                "baseline",
                sev,
                f"new server {srv} never seen in this agent's baseline",
                "behavioral novelty -- the agent dialed a destination outside its profile",
                owasp_asi="ASI10",
                mitre_atlas="AML.T0053",
            )
        )
    ceiling = ctx.baseline.get("max_connects")
    if isinstance(ceiling, int) and not isinstance(ceiling, bool):
        count = len(ctx.dialed())
        if count > ceiling:
            findings.append(
                Finding(
                    "baseline",
                    sev,
                    f"connect volume {count} exceeds baseline ceiling {ceiling}",
                    "behavioral novelty -- abnormal connect volume for this agent",
                    owasp_asi="ASI10",
                    mitre_atlas="AML.T0053",
                )
            )
    return findings


# The registry: lens name -> pure function. Stable iteration order is the tuple in
# profile.ALL_LENSES; the engine iterates the profile's enabled subset.
REGISTRY: dict[str, Callable[[AgentContext, AnalysisProfile], list[Finding]]] = {
    "egress": lens_egress,
    "dns": lens_dns,
    "credential": lens_credential,
    "doh": lens_doh,
    "process": lens_process,
    "said_scope": lens_said_scope,
    "sequence": lens_sequence,
    "baseline": lens_baseline,
}
