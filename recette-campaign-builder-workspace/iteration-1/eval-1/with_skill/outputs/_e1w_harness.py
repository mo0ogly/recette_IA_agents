"""Sibling harness for the e1w_soc_containment campaign.

Validates ONLY campaigns/bnp/e1w_soc_containment.campaign.json via an
isolated temp-dir run.  Does NOT touch any committed catalog or policy.

Two actions under test:
  - okta/suspend_user   -> soc_agent -> ALLOW
    (okta/suspend_user is in the committed catalog; the bundle rule grants ALLOW
    to soc_agent via EXTRA_RULES)
  - cloud/isolate_host  -> soc_agent -> ESCALATE
    (cloud/isolate_host is absent from the committed catalog; an in-memory
    EXTRA_SPEC registers it, then the bundle rule grants ESCALATE to soc_agent)

Usage: /home/fpizzi/recette_agentrail/.venv/bin/python scripts/_e1w_harness.py
Exit 0 = ALL PASS, 1 = FAILURES PRESENT.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports shared with run_bnp_scenarios (same patterns, minimal subset)
# ---------------------------------------------------------------------------
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

# Bundle version -- unique to this harness so it never collides with bnp-v1.
BUNDLE_VERSION = "e1w-soc-v1"

# ---------------------------------------------------------------------------
# Extra ActionSpec -- cloud/isolate_host is absent from the committed catalog.
# okta/suspend_user is committed; no spec needed for it.
# ---------------------------------------------------------------------------

EXTRA_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec(
        target_system="cloud",
        action_type="isolate_host",
        risk_level=RiskLevel.HIGH,
        verdict_privileged=PolicyVerdict.ESCALATE,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=("cloud_admin",),
        description="Network-isolate a host (incident containment). High blast radius on shared infra.",
    ),
)

# ---------------------------------------------------------------------------
# Extra policy rules -- contextual grants for the soc_agent role.
#   suspend_user -> ALLOW  (reversible, no human gate required)
#   isolate_host -> ESCALATE (high blast radius, analyst approval required)
# ---------------------------------------------------------------------------

EXTRA_RULES: tuple[tuple[str, str, str, PolicyVerdict, RiskLevel], ...] = (
    ("okta", "suspend_user", "soc_agent", PolicyVerdict.ALLOW, RiskLevel.HIGH),
    ("cloud", "isolate_host", "soc_agent", PolicyVerdict.ESCALATE, RiskLevel.HIGH),
)


# ---------------------------------------------------------------------------
# Stub proxy -- deterministic, zero network I/O (I5)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Catalog and bundle builders
# ---------------------------------------------------------------------------

def build_extended_catalog() -> Catalog:
    """Committed catalog + the one extra spec for cloud/isolate_host."""
    return Catalog(tuple(load_catalog().all()) + EXTRA_SPECS)


def build_bundle(catalog: Catalog) -> PolicyVersion:
    """Baseline from the extended catalog + contextual soc_agent grants."""
    base = baseline_from_catalog(catalog, version=BUNDLE_VERSION)
    extra = tuple(
        PolicyRule(
            rule_id=f"e1w.{target}.{action}.{role}",
            target_system=target,
            action_type=action,
            role=role,
            verdict=verdict,
            risk_level=risk,
        )
        for target, action, role, verdict, risk in EXTRA_RULES
    )
    return PolicyVersion(version=BUNDLE_VERSION, rules=base.rules + extra)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    from fastapi.testclient import TestClient

    campaign_path = Path("campaigns/bnp/e1w_soc_containment.campaign.json")
    if not campaign_path.exists():
        print(f"ERROR: campaign file not found: {campaign_path}", file=sys.stderr)
        return 1

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

        doc = load_campaign(campaign_path)
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

        if report.chain_ok is False:
            print("    audit chain: BROKEN")
        elif report.chain_ok is True:
            print("    audit chain: intact")

        total = 1
        print(f"\n{'ALL PASS' if report.ok else 'FAILURES PRESENT'} -- {total} campaign")
        return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
