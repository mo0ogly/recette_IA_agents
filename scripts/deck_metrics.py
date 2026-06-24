"""Single source of truth for the presentation deck "En chiffres" table.

The deck (docs/tracking/docx_build/build*.js) used to hand-type corpus counts,
which silently drifted as the corpus grew (e.g. AnnexC 124 -> 148, discovery
20 -> 22, red-team 15 -> 13). This emitter derives every number from the code
so the deck can never go stale again: run it, paste the numbers (or wire the
build to read the JSON).

Deterministic (I4): pure counting over the catalog / corpus / registries, no
clock, no network. Run: ``python3 -m scripts.deck_metrics`` (or
``python3 scripts/deck_metrics.py``). Output: one JSON object on stdout.
"""

from __future__ import annotations

import json
import pkgutil
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CORPUS = _ROOT / "corpus"


def _actions() -> dict[str, int]:
    from recette.tools import agent_action_catalog

    cat = agent_action_catalog()
    systems = {a.get("target_system") for a in cat}
    return {"actions": len(cat), "systems": len(systems)}


def _templates() -> dict[str, object]:
    from recette.api.campaign_templates import list_templates

    lt = list_templates()
    by_profile: dict[str, int] = {}
    for t in lt:
        by_profile[t.get("profile", "?")] = by_profile.get(t.get("profile", "?"), 0) + 1
    systems = {t.get("target_system") for t in lt if t.get("target_system")}
    return {"templates": len(lt), "template_profiles": by_profile, "template_systems": len(systems)}


def _providers() -> int:
    from recette.llm._registry import _PROVIDERS

    return len(_PROVIDERS)


def _annex_c() -> dict[str, object]:
    """Criticality-tagged catalog specs, deduped by (system, action)."""
    from recette.platform.catalog import domains

    seen: set[tuple[str, str]] = set()
    by_level: dict[str, int] = {}
    for mod_info in pkgutil.iter_modules(domains.__path__):
        mod = __import__(f"recette.platform.catalog.domains.{mod_info.name}", fromlist=["_"])
        for name in dir(mod):
            obj = getattr(mod, name)
            if not isinstance(obj, (list, tuple)):
                continue
            for item in obj:
                action = getattr(item, "action_type", None) or getattr(item, "action", None)
                system = (
                    getattr(item, "target_system", None)
                    or getattr(item, "system", None)
                    or mod_info.name
                )
                crit = getattr(item, "criticality", None)
                if not (crit and action):
                    continue
                key = (str(system), str(action))
                if key in seen:
                    continue
                seen.add(key)
                level = str(crit).split(".")[-1].strip("'>")
                by_level[level] = by_level.get(level, 0) + 1
    return {"annex_c_total": len(seen), "annex_c_by_level": dict(sorted(by_level.items()))}


def _discovery() -> dict[str, object]:
    from recette.discovery_harness import SURFACE_CORPUS, SURFACE_ORDER, discover_repo_dirs

    per_surface: dict[str, int] = {}
    surfaces = dict(SURFACE_CORPUS)
    surfaces.setdefault("github", _CORPUS / "repos")
    for surface in SURFACE_ORDER:
        directory = surfaces.get(surface)
        if directory is None:
            continue
        per_surface[surface] = len(list(discover_repo_dirs(directory)))
    return {"discovery_total": sum(per_surface.values()), "discovery_per_surface": per_surface}


def _redteam() -> dict[str, int]:
    sim = _CORPUS / "sim"
    maf = len(list(sim.glob("*.scenario.json")))
    git = len(list(sim.glob("*.git-scenario.json")))
    return {"redteam_total": maf + git, "redteam_maf": maf, "redteam_git": git}


def _corpus_counts() -> dict[str, int]:
    identification = len(list((_CORPUS / "agents").glob("*/*/manifest.json")))
    campaigns = len(list((_ROOT / "campaigns").rglob("*.campaign.json")))
    return {"identification_subjects": identification, "campaigns": campaigns}


def _config_counts() -> dict[str, int]:
    cfg_path = _ROOT / "config" / "inspect_ia_agents.config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return {
        "agents_runtime": len(cfg.get("agents", [])),
        "servers": len(cfg.get("servers", [])),
        "ai_backends": len(cfg.get("ai_backends", [])),
    }


def collect() -> dict[str, object]:
    """All deck metrics, derived from the code (the single source of truth)."""
    out: dict[str, object] = {}
    out.update(_actions())
    out.update(_templates())
    out["providers"] = _providers()
    out.update(_annex_c())
    out.update(_discovery())
    out.update(_redteam())
    out.update(_corpus_counts())
    out.update(_config_counts())
    return out


def main() -> None:
    print(json.dumps(collect(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
