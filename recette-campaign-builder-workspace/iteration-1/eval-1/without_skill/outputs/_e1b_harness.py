"""Harness for bnp-e1b-soc-containment campaign validation.

Validates only campaigns/bnp/e1b_soc_containment.campaign.json.
Uses the same extended catalog and bnp-v1 policy bundle as run_bnp_scenarios.py
(in-memory only, no committed file modifications).

Usage: /home/fpizzi/recette_agentrail/.venv/bin/python scripts/_e1b_harness.py
Exit 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Ensure repo root is on sys.path regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from recette.api.app import create_app
from recette.api.config_store import ConfigStore
from recette.campaign import CampaignRunner, load_campaign
from recette.platform.catalog import Catalog, load_catalog
from recette.platform.catalog.model import ActionSpec, RiskLevel
from recette.platform.events import PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.policy.model import PolicyRule, PolicyVersion, baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

BUNDLE_VERSION = "bnp-v1"

CAMPAIGN_PATH = _REPO_ROOT / "campaigns" / "bnp" / "e1b_soc_containment.campaign.json"


# ---------------------------------------------------------------------------
# Helpers: mirror run_bnp_scenarios.py constructors exactly.
# ---------------------------------------------------------------------------

def _esc_spec(
    target: str, action: str, risk: RiskLevel, privileged_role: str, description: str
) -> ActionSpec:
    """A sensitive action: escalate for its admin role, deny for everyone else."""
    return ActionSpec(
        target_system=target,
        action_type=action,
        risk_level=risk,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(privileged_role,),
        description=description,
    )


def _deny_spec(target: str, action: str, risk: RiskLevel, description: str) -> ActionSpec:
    """A pure deny-for-all action (no privileged escape hatch)."""
    return ActionSpec(
        target_system=target,
        action_type=action,
        risk_level=risk,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description=description,
    )


# BNP actions absent from the 11 committed domains (added in memory only).
EXTRA_SPECS: tuple[ActionSpec, ...] = (
    _esc_spec("okta", "revoke_long_lived_token", RiskLevel.HIGH, "identity_admin",
              "Revoke a long-lived token (defensive containment)."),
    _deny_spec("okta", "assume_delegation", RiskLevel.CRITICAL,
               "Act on behalf of another agent via delegation."),
    _esc_spec("cloud", "isolate_host", RiskLevel.HIGH, "cloud_admin",
              "Network-isolate a host (incident containment)."),
    _esc_spec("github", "read_cicd_secrets", RiskLevel.HIGH, "devops_admin",
              "Read a secret from the CI/CD environment."),
    _esc_spec("mcp", "invoke_tool", RiskLevel.HIGH, "mcp_admin",
              "Invoke a tool exposed by an MCP server."),
    _esc_spec("finance", "freeze_operation", RiskLevel.HIGH, "finance_admin",
              "Temporarily freeze a financial operation (fraud hold)."),
    _esc_spec("comms", "notify_customer", RiskLevel.MEDIUM, "comms_admin",
              "Notify a customer via an authenticated channel."),
    _esc_spec("compliance", "open_kyc_review", RiskLevel.MEDIUM, "compliance_admin",
              "Open a KYC compliance review workflow."),
)

# Contextual grants: (target, action, role) -> verdict for the scenario roles.
EXTRA_RULES: tuple[tuple[str, str, str, PolicyVerdict, RiskLevel], ...] = (
    ("okta", "suspend_user", "soc_agent", PolicyVerdict.ALLOW, RiskLevel.HIGH),
    ("okta", "revoke_api_key", "soc_agent", PolicyVerdict.ALLOW, RiskLevel.HIGH),
    ("okta", "revoke_long_lived_token", "soc_agent", PolicyVerdict.ALLOW, RiskLevel.HIGH),
    ("cloud", "isolate_host", "soc_agent", PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("support_desk", "export_customer_conversations", "support_agent",
     PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("mcp", "invoke_tool", "mcp_agent", PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("github", "read_cicd_secrets", "mcp_agent", PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("github", "deploy_production", "devops_agent", PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("okta", "add_user_to_admin_group", "scoped_agent", PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("okta", "create_api_key", "integration_admin", PolicyVerdict.ALLOW, RiskLevel.HIGH),
    ("okta", "modify_oauth_scopes", "integration_admin", PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("okta", "generate_long_lived_token", "integration_admin",
     PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("finance", "freeze_operation", "fraud_monitor", PolicyVerdict.ESCALATE, RiskLevel.HIGH),
    ("comms", "notify_customer", "fraud_monitor", PolicyVerdict.ALLOW, RiskLevel.MEDIUM),
    ("compliance", "open_kyc_review", "kyc_agent", PolicyVerdict.ALLOW, RiskLevel.MEDIUM),
)


class _StubProxy:
    """Deterministic external-system proxy (I5): never calls the network."""

    def execute(self, event):  # type: ignore[no-untyped-def]
        response = {"done": True}
        return ExecutionResult(
            ok=True,
            status_code=200,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )


def build_extended_catalog() -> Catalog:
    return Catalog(tuple(load_catalog().all()) + EXTRA_SPECS)


def build_bundle(catalog: Catalog) -> PolicyVersion:
    base = baseline_from_catalog(catalog, version=BUNDLE_VERSION)
    extra = tuple(
        PolicyRule(
            rule_id=f"bnp.{target}.{action}.{role}",
            target_system=target,
            action_type=action,
            role=role,
            verdict=verdict,
            risk_level=risk,
        )
        for target, action, role, verdict, risk in EXTRA_RULES
    )
    return PolicyVersion(version=BUNDLE_VERSION, rules=base.rules + extra)


def main() -> int:
    from fastapi.testclient import TestClient

    catalog = build_extended_catalog()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        policies = PolicyStore(tmp / "policies")
        policies.publish(build_bundle(catalog))
        policies.set_active(BUNDLE_VERSION)
        app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=policies,
            proxy=_StubProxy(),
            catalog=catalog,
        )
        client = TestClient(app)
        runner = CampaignRunner(client)

        doc = load_campaign(CAMPAIGN_PATH)
        report = runner.run(doc)

        status = "PASS" if report.ok else "FAIL"
        counts = ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items()) if v)
        print(f"[{status}] {report.name}  ({counts})")
        for r in report.results:
            mark = "ok " if r.matches_expectation else "MISS"
            extra = "" if r.matches_expectation else f"  expected={r.expected_verdict}"
            print(
                f"    {mark} {r.target_system}/{r.action_type} -> "
                f"{r.verdict}/{r.approval_state}{extra}"
            )
            if r.rationale:
                print(f"         rationale: {r.rationale}")
        chain_label = "intact" if report.chain_ok else "BROKEN"
        print(f"    audit chain: {chain_label} ({report.chain_checked} events checked)")

        if not report.ok:
            print("\nFAILURES PRESENT")
            for r in report.mismatches:
                print(f"  MISMATCH: {r.target_system}/{r.action_type} "
                      f"got={r.verdict} expected={r.expected_verdict}")
            return 1

        print(f"\nALL PASS -- 1 campaign")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
