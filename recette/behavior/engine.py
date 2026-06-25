"""Wave runner -- apply an ``AnalysisProfile`` to an ``EvidenceBundle``.

``run_wave`` is a pure function of ``(bundle, profile)`` (I4): it builds each
agent's ordered annotated wire, runs the profile's enabled lenses, aggregates a
behavioral score, and returns a deterministic ``AnalysisReport`` with provenance.
``replay`` re-runs and asserts byte-equality against a prior report -- the research
reproducibility guarantee, and a regression test.
"""

from __future__ import annotations

import json

from ..surface.netmap import annotate_token
from .evidence import EvidenceBundle, build_endpoint_inputs
from .lenses import REGISTRY, AgentContext
from .profile import ALL_LENSES, AnalysisProfile
from .report import TOOL_VERSION, AgentReport, AnalysisReport, Finding

# Base behavioral-score penalty per severity, before the threat weight multiplier.
_PENALTY = {"alert": 30, "warn": 12, "info": 0}


def _cohort_match(agent_id: str, profile: AnalysisProfile) -> bool:
    """Whether an agent is in the wave's cohort. ``["*"]`` (default) = all."""
    selector = profile.cohort.get("agents", ["*"])
    if not isinstance(selector, list) or "*" in selector:
        return True
    return agent_id in selector


def _behavioral_score(findings: list[Finding], profile: AnalysisProfile) -> int:
    """100 minus the threat-weighted severity penalty, clamped to [0, 100]. Pure,
    integer result so the report serializes byte-identically on replay."""
    penalty = 0.0
    for f in findings:
        penalty += _PENALTY.get(f.severity, 0) * profile.lens_weight(f.lens)
    return max(0, 100 - int(round(penalty)))


def _done_view(annotations: list[dict]) -> dict:
    from ..surface.agent_analysis import _doh_host
    from .lenses import AgentContext as _Ctx

    ctx = _Ctx("_", annotations)
    creds = sorted({p for p in ctx.opens() if _is_credential(p)})
    doh = sorted({h for ep in ctx.undeclared_egress() if (h := _doh_host(ep))})
    return {
        "dialed_servers": sorted(set(ctx.dialed())),
        "undeclared_egress": sorted(set(ctx.undeclared_egress())),
        "undeclared_dns": sorted(set(ctx.undeclared_dns())),
        "process_spawned": any(a.get("kind") in ("fork", "exec") for a in annotations),
        "credential_opens": creds,
        "doh_egress": doh,
    }


def _is_credential(path: str) -> bool:
    from ..surface.agent_analysis import _is_credential_path

    return _is_credential_path(path)


def run_wave(bundle: EvidenceBundle, profile: AnalysisProfile) -> AnalysisReport:
    """Run one analysis wave. Deterministic; raises ValueError on a bad profile."""
    profile.validate()
    endpoint_map, dns_names = build_endpoint_inputs(bundle.servers)
    enabled = [name for name in ALL_LENSES if name in profile.lenses and name in REGISTRY]

    agents: list[AgentReport] = []
    for agent_id in bundle.agent_ids():
        if not _cohort_match(agent_id, profile):
            continue
        tokens = bundle.wire_tokens(agent_id)
        annotations = [annotate_token(t, endpoint_map, dns_names) for t in tokens]
        declared = bundle.declared.get(agent_id, {}) or {}
        ctx = AgentContext(
            agent_id=agent_id,
            annotations=annotations,
            declared=declared,
            baseline=bundle.baselines.get(agent_id),
        )
        findings: list[Finding] = []
        for name in enabled:
            findings.extend(REGISTRY[name](ctx, profile))

        decided = declared.get("decided")
        planned = {
            "systems": sorted(set(declared.get("systems", []) or [])),
            "scope": sorted(set(declared.get("scope", []) or [])),
        }
        said = {"actions": sorted(set(decided))} if decided is not None else None
        coherent = not any(f.severity in ("alert", "warn") for f in findings)
        agents.append(
            AgentReport(
                agent_id=agent_id,
                identified=bool(annotations),
                coherent=coherent,
                behavioral_score=_behavioral_score(findings, profile),
                planned=planned,
                said=said,
                done=_done_view(annotations),
                findings=findings,
            )
        )

    return AnalysisReport(
        profile_name=profile.name,
        threat=profile.threat,
        evidence_hash=bundle.evidence_hash(),
        profile_hash=profile.profile_hash(),
        tool_version=TOOL_VERSION,
        agents=agents,
    )


def replay(bundle: EvidenceBundle, profile: AnalysisProfile, prior: dict) -> bool:
    """Re-run the wave and assert the report is byte-identical to ``prior`` (a
    previously serialized ``AnalysisReport.to_dict()``). The reproducibility proof."""
    current = run_wave(bundle, profile).to_dict()
    return json.dumps(current, sort_keys=True) == json.dumps(prior, sort_keys=True)
