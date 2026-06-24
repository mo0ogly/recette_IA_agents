"""Generate per-domain coverage campaigns: every catalogued action, asserted.

Reads the committed catalog and emits one campaign per domain into
campaigns/coverage/. Each campaign runs the domain's privileged role over EVERY
action of that domain, asserting the catalog's documented posture
(verdict_privileged: escalate for governed actions, deny for pure-deny rows).
Together the campaigns cover every catalogued action and prove the
engine/catalog produce the documented verdict for each one.

No EXTRA_SPECS/EXTRA_RULES needed: baseline_from_catalog already materializes the
privileged-role rule for every governed action, and pure-deny rows fall to the
catalog default. So run_banque_scenarios.py validates these as-is.

Usage: python3 scripts/gen_coverage_campaigns.py [--out campaigns/coverage]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from recette.platform.catalog import load_catalog
from recette.platform.catalog.model import ActionSpec

_PRIV_ROLE = {
    "okta": "identity_admin",
    "cloud": "cloud_admin",
    "github": "devops_admin",
    "data_platform": "data_admin",
    "finance": "finance_admin",
    "crm": "sales_admin",
    "slack": "workspace_admin",
    "support_desk": "support_admin",
    "hris": "hr_admin",
    "legal_dms": "legal_admin",
    "product_cms": "product_admin",
    "knowledge_base": "rag_agent",
    "mcp": "tool_operator",
    "comms": "comms_admin",
    "compliance": "compliance_admin",
    "gitlab": "devops_admin",
}


_VERDICT_GLOSS = {
    "allow": "least-privilege grant",
    "escalate": "human approval gate",
    "deny": "deny-by-default",
}


def _campaign_for(domain: str, role: str, specs: list[ActionSpec]) -> dict:
    n_allow = sum(1 for s in specs if s.verdict_privileged == "allow")
    n_esc = sum(1 for s in specs if s.verdict_privileged == "escalate")
    n_deny = len(specs) - n_esc - n_allow
    actions = []
    for s in sorted(specs, key=lambda x: x.action_type):
        verdict = str(s.verdict_privileged)
        actions.append(
            {
                "agent_id": f"cov-{domain}-admin",
                "target_system": domain,
                "action_type": s.action_type,
                "resource": f"{domain}/{s.action_type}/sample",
                "payload": {"criticality": s.risk_level},
                "expect": verdict,
                "rationale": (
                    f"{s.risk_level.upper()} action; privileged role {role} -> {verdict} "
                    f"({_VERDICT_GLOSS.get(verdict, verdict)})."
                ),
            }
        )
    return {
        "name": f"coverage-{domain}",
        "objective": (
            f"Coverage recette for the {domain} domain: the privileged role {role} exercises "
            f"every one of its {len(specs)} catalogued actions, asserting the documented posture "
            f"({n_allow} allow, {n_esc} escalate, {n_deny} deny). Proves the catalog/engine emit "
            f"the right verdict for each action of this domain."
        ),
        "teaching": (
            f"The {role} gets a verdict matching the risk, never a blanket grant: a low-risk "
            f"routine action is allowed (least-privilege), a sensitive action escalates to a human "
            f"(I6), a pure-deny action stays denied for everyone. The whole sweep is replayable "
            f"for audit (I4)."
        ),
        "agents": [
            {
                "id": f"cov-{domain}-admin",
                "runtime": "lab",
                "role": role,
                "capability_scope": [domain],
                "model": "claude-opus-4-8",
                "system_prompt": f"You are the privileged {role} agent for the {domain} system.",
            }
        ],
        "actions": actions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_coverage_campaigns")
    parser.add_argument("--out", default="campaigns/coverage")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    by_domain: dict[str, list[ActionSpec]] = defaultdict(list)
    for spec in load_catalog().all():
        by_domain[spec.target_system].append(spec)

    total_actions = 0
    for domain, specs in sorted(by_domain.items()):
        role = _PRIV_ROLE[domain]
        doc = _campaign_for(domain, role, specs)
        path = out / f"coverage-{domain}.campaign.json"
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        total_actions += len(specs)
        print(f"wrote {path}  ({len(specs)} actions, role={role})")

    print(f"\n{len(by_domain)} campaigns, {total_actions} actions covered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
