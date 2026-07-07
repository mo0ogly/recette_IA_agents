"""Server-side grounding for the assist contextual-help endpoint.

The console's AI help buttons send only a TOPIC KEY (+ id params); the data
the LLM is grounded on is resolved HERE, from the app.state stores -- never
trusted from the client. Each topic function returns a compact dict built
through an EXPLICIT FIELD ALLOWLIST (never dict(**entry)), so store fields
that must not reach an external LLM (secrets are already isolated by R8, but
also prompts, tokens, internal paths) cannot leak by accident.

Output size is bounded twice: per-topic item caps here, then the router
truncates the serialized block to MAX_UNTRUSTED_CHARS and fences it with
wrap_untrusted before it enters the prompt (injection guard).

Diagnostic path (I4 N/A), read-only over the stores.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

MAX_LIST_ITEMS = 30


class _AppState(Protocol):
    config_store: Any
    verdict_store: Any
    recette_campaign_catalog: Any


def _agent_summary(agent: dict[str, Any]) -> dict[str, Any]:
    """Allowlisted view of one configured agent (no prompts, no ground truth)."""
    return {
        "id": agent.get("id"),
        "role": agent.get("role"),
        "runtime": agent.get("runtime"),
        "target_system": agent.get("target_system"),
        "goal": agent.get("goal"),
        "ai_mode": agent.get("ai_mode"),
        "capability_scope": agent.get("capability_scope"),
    }


def _topic_dashboard_overview(state: _AppState, params: dict[str, str]) -> dict[str, Any]:
    cfg = state.config_store.read()
    campaigns = state.recette_campaign_catalog.list()
    latest = state.verdict_store.latest()
    verdict_summary: dict[str, Any] | None = None
    if latest is not None:
        judged = latest.get("judged") or []
        statuses = [entry.get("status") for entry in judged]
        verdict_summary = {
            "judged_agents": len(judged),
            "pass": statuses.count("PASS"),
            "fail": statuses.count("FAIL"),
            "skip": statuses.count("SKIP"),
        }
    return {
        "agents_configured": len(cfg.get("agents", [])),
        "ai_backends": len(cfg.get("ai_backends", [])),
        "target_servers": len(cfg.get("servers", [])),
        "recette_campaigns": len(campaigns),
        "latest_verdict_submission": verdict_summary,
    }


def _topic_agents_list(state: _AppState, params: dict[str, str]) -> dict[str, Any]:
    agents = state.config_store.read().get("agents", [])
    return {
        "count": len(agents),
        "agents": [_agent_summary(agent) for agent in agents[:MAX_LIST_ITEMS]],
    }


def _topic_agents_detail(state: _AppState, params: dict[str, str]) -> dict[str, Any]:
    agent = state.config_store.get_agent(params["agent_id"])
    if agent is None:
        return {"agent_id": params["agent_id"], "found": False}
    summary = _agent_summary(agent)
    summary["found"] = True
    summary["scenario_steps"] = len(agent.get("scenario") or [])
    ground_truth = agent.get("ground_truth") or {}
    # Only the coarse expectations, never the full ground-truth document.
    summary["ground_truth_declares"] = sorted(ground_truth.keys())
    return summary


def _topic_campaigns_list(state: _AppState, params: dict[str, str]) -> dict[str, Any]:
    campaigns = state.recette_campaign_catalog.list()
    families: dict[str, int] = {}
    for campaign in campaigns:
        family = str(campaign.get("family", "root"))
        families[family] = families.get(family, 0) + 1
    return {
        "count": len(campaigns),
        "families": families,
        "campaigns": [
            {
                "id": c.get("id"),
                "family": c.get("family"),
                "name": c.get("name"),
                "action_count": c.get("action_count"),
            }
            for c in campaigns[:MAX_LIST_ITEMS]
        ],
    }


def _topic_campaigns_detail(state: _AppState, params: dict[str, str]) -> dict[str, Any]:
    doc = state.recette_campaign_catalog.get(params["campaign_id"])
    if doc is None:
        return {"campaign_id": params["campaign_id"], "found": False}
    actions = doc.get("actions") or []
    return {
        "found": True,
        "id": params["campaign_id"],
        "name": doc.get("name"),
        "objective": doc.get("objective"),
        "teaching": doc.get("teaching"),
        "action_count": len(actions),
        "actions": [
            {
                "agent_id": a.get("agent_id"),
                "action_type": a.get("action_type"),
                "target_system": a.get("target_system"),
                "expected_verdict": a.get("expect"),
            }
            for a in actions[:MAX_LIST_ITEMS]
        ],
    }


def _topic_verdicts_recent(state: _AppState, params: dict[str, str]) -> dict[str, Any]:
    latest = state.verdict_store.latest()
    if latest is None:
        return {"submissions": 0, "latest": None}
    judged = latest.get("judged") or []
    return {
        "submissions": len(state.verdict_store.history()),
        "latest": {
            "tool": latest.get("tool"),
            "judged": [
                {
                    "agent_id": entry.get("agent_id"),
                    "status": entry.get("status"),
                    "failed_checks": sorted(
                        name for name, ok in (entry.get("checks") or {}).items() if not ok
                    ),
                }
                for entry in judged[:MAX_LIST_ITEMS]
            ],
        },
    }


def _topic_redteam_summary(state: _AppState, params: dict[str, str]) -> dict[str, Any]:
    # The sim router already summarizes the committed red-team corpus (pure
    # functions over corpus files); reuse it instead of re-reading the corpus.
    from .routers.sim import list_git_scenarios, list_scenarios

    scenarios = list_scenarios() + list_git_scenarios()
    owasp: dict[str, int] = {}
    caught = 0
    for scenario in scenarios:
        tag = str((scenario.get("tags") or {}).get("owasp_asi", "untagged"))
        owasp[tag] = owasp.get(tag, 0) + 1
        if scenario.get("anomaly_caught"):
            caught += 1
    return {
        "scenario_count": len(scenarios),
        "anomalies_caught": caught,
        "owasp_asi_distribution": dict(sorted(owasp.items())),
        "scenarios": [
            {
                "scenario_id": s.get("scenario_id"),
                "verdict": s.get("verdict"),
                "expected_verdict": s.get("expected_verdict"),
                "violation_type": s.get("violation_type"),
            }
            for s in scenarios[:MAX_LIST_ITEMS]
        ],
    }


def _topic_runs_recent(state: Any, params: dict[str, str]) -> dict[str, Any]:
    runs = state.run_manager.list()
    return {
        "count": len(runs),
        "runs": [
            {
                "id": run.id,
                "kind": run.kind,
                "status": run.status,
                "created_at": run.created_at,
                "error": run.error,
            }
            for run in runs[:MAX_LIST_ITEMS]
        ],
    }


def _topic_proxy_recent(state: Any, params: dict[str, str]) -> dict[str, Any]:
    traces = state.proxy_store.snapshot_traces()
    return {
        "trace_count": len(traces),
        "traces": [
            {
                "agent_id": t.agent_id,
                "target_system": t.target_system,
                "action_type": t.action_type,
                "resource": t.resource,
                "ok": t.ok,
            }
            for t in traces[-MAX_LIST_ITEMS:]
        ],
    }


def _topic_rag_kb(state: Any, params: dict[str, str]) -> dict[str, Any]:
    documents = state.kb_store.documents()
    return {
        "document_count": len(documents),
        "documents": [
            {
                "id": doc.get("id"),
                "title": doc.get("title"),
                "scenario": doc.get("scenario"),
                "poisoned": doc.get("poisoned"),
            }
            for doc in documents[:MAX_LIST_ITEMS]
        ],
    }


def _topic_ai_backends_list(state: Any, params: dict[str, str]) -> dict[str, Any]:
    backends = state.config_store.read().get("ai_backends", [])
    secret_store = getattr(state, "secret_store", None)
    return {
        "count": len(backends),
        "backends": [
            {
                "id": b.get("id"),
                "provider": b.get("provider"),
                "model": b.get("model"),
                # Boolean only, never the key (R8).
                "key_configured": bool(
                    secret_store is not None and secret_store.is_configured(str(b.get("id")))
                ),
            }
            for b in backends[:MAX_LIST_ITEMS]
        ],
    }


def _topic_runs_run(state: Any, params: dict[str, str]) -> dict[str, Any]:
    from ..runs.registry import RunRegistry

    registry = getattr(state, "runs_registry", None) or RunRegistry()
    run_id = params["run_id"]
    try:
        run = registry.read_run(run_id)
    except KeyError:
        return {"run_id": run_id, "found": False}
    meta = run.get("meta") or {}
    annotations = run.get("annotations") or {}
    return {
        "found": True,
        "id": meta.get("id"),
        "kind": meta.get("kind"),
        "eurodate": meta.get("eurodate"),
        "status": meta.get("status"),
        "parent_group": meta.get("parent_group"),
        "artifacts": [a.get("file") for a in (meta.get("artifacts") or [])[:MAX_LIST_ITEMS]],
        "tags": annotations.get("tags"),
        "label": annotations.get("label"),
    }


def _topic_proxy_trace(state: Any, params: dict[str, str]) -> dict[str, Any]:
    wanted = params["trace_id"]
    for trace in reversed(state.proxy_store.snapshot_traces()):
        if trace.event_id == wanted or str(trace.seq) == wanted:
            return {
                "found": True,
                "event_id": trace.event_id,
                "agent_id": trace.agent_id,
                "target_system": trace.target_system,
                "target": trace.target,
                "action_type": trace.action_type,
                "resource": trace.resource,
                "ok": trace.ok,
            }
    return {"trace_id": wanted, "found": False}


def _topic_audit_recent(state: Any, params: dict[str, str]) -> dict[str, Any]:
    events = state.event_store.read_from(0)
    kinds: dict[str, int] = {}
    for event in events:
        kind = str(getattr(event, "kind", "unknown"))
        kinds[kind] = kinds.get(kind, 0) + 1
    recent = events[-MAX_LIST_ITEMS:]
    return {
        "event_count": len(events),
        "kinds": dict(sorted(kinds.items())),
        "recent": [
            {
                "event_id": getattr(e, "event_id", None),
                "kind": str(getattr(e, "kind", "unknown")),
                "agent_id": getattr(e, "agent_id", None),
                "verdict": getattr(e, "verdict", None),
                "action_type": getattr(e, "action_type", None),
            }
            for e in recent
        ],
    }


# topic key -> (label fr, required params, grounding fn). The label feeds
# GET /assist/topics (the console introspection + the Prompts IA page table).
TOPICS: dict[str, dict[str, Any]] = {
    "dashboard.overview": {
        "label": "Vue d'ensemble de la plateforme",
        "params": [],
        "ground": _topic_dashboard_overview,
    },
    "agents.list": {
        "label": "Agents de recette configures",
        "params": [],
        "ground": _topic_agents_list,
    },
    "agents.detail": {
        "label": "Detail d'un agent",
        "params": ["agent_id"],
        "ground": _topic_agents_detail,
    },
    "campaigns.list": {
        "label": "Catalogue des campagnes de recette",
        "params": [],
        "ground": _topic_campaigns_list,
    },
    "campaigns.detail": {
        "label": "Detail d'une campagne",
        "params": ["campaign_id"],
        "ground": _topic_campaigns_detail,
    },
    "verdicts.recent": {
        "label": "Derniere soumission de verdicts",
        "params": [],
        "ground": _topic_verdicts_recent,
    },
    "redteam.summary": {
        "label": "Synthese red-team (/sim)",
        "params": [],
        "ground": _topic_redteam_summary,
    },
    "runs.recent": {
        "label": "Runs recents",
        "params": [],
        "ground": _topic_runs_recent,
    },
    "proxy.recent": {
        "label": "Traces proxy recentes",
        "params": [],
        "ground": _topic_proxy_recent,
    },
    "rag.kb": {
        "label": "Base de connaissances RAG",
        "params": [],
        "ground": _topic_rag_kb,
    },
    "ai_backends.list": {
        "label": "Backends IA configures",
        "params": [],
        "ground": _topic_ai_backends_list,
    },
    "audit.recent": {
        "label": "Journal d'audit recent",
        "params": [],
        "ground": _topic_audit_recent,
    },
    "runs.run": {
        "label": "Detail d'un run",
        "params": ["run_id"],
        "ground": _topic_runs_run,
    },
    "proxy.trace": {
        "label": "Detail d'une trace proxy",
        "params": ["trace_id"],
        "ground": _topic_proxy_trace,
    },
}


def topics_catalog() -> list[dict[str, Any]]:
    """Introspection payload for GET /assist/topics."""
    return [
        {"topic": key, "label": spec["label"], "params": list(spec["params"])}
        for key, spec in TOPICS.items()
    ]


def ground_topic(state: _AppState, topic: str, params: dict[str, str]) -> str | None:
    """Resolve one topic's grounding data as a JSON string, or None if the
    topic is unknown. Only the declared params are read (an unexpected client
    param is silently dropped -- never echoed into the grounding)."""
    spec = TOPICS.get(topic)
    if spec is None:
        return None
    allowed = {name: str(params.get(name, "")) for name in spec["params"]}
    data = spec["ground"](state, allowed)
    return json.dumps(data, ensure_ascii=False)
