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
