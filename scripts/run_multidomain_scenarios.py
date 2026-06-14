"""Run the multi-domain composed campaigns as governed campaigns and check verdicts.

Like scripts/run_bnp_scenarios.py, this harness touches no LLM: every action flows
through the real gateway (policy decide -> deny / escalate -> pending / allow ->
execute), proving the governance posture (ALLOW/ESCALATE/DENY) each campaign claims.

It layers on the committed catalog, in memory only, the gitlab git-family read
actions (gitlab has no governance catalog of its own) and grants them ALLOW for the
devops role, so a legit read-only sweep can include gitlab. Everything else uses the
committed catalog's baseline verdicts (allow-path reads for the privileged role,
escalate for sensitive privileged actions, deny-by-default otherwise).

Usage: python3 scripts/run_multidomain_scenarios.py [--dir campaigns/multidomain]
Exit 0 if every campaign matches its expectations and the audit chain is intact.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import cast

from recette.api.app import create_app
from recette.api.config_store import ConfigStore
from recette.campaign import CampaignRunner, HttpClient, load_campaign
from recette.platform.catalog import Catalog, load_catalog
from recette.platform.catalog.model import ActionSpec, Criticality, RiskLevel
from recette.platform.events import PolicyVerdict
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.policy.model import PolicyRule, PolicyVersion, baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

BUNDLE_VERSION = "multidomain-v1"


def _read_spec(target: str, action: str, privileged_role: str, description: str) -> ActionSpec:
    """An allow-path read action: ALLOW for its admin role, deny for everyone else.
    baseline_from_catalog turns verdict_privileged into the role's rule, so no
    extra bundle rule is needed (an appended rule would lose to the baseline's
    first-match for the same privileged role)."""
    return ActionSpec(
        target_system=target,
        action_type=action,
        risk_level=RiskLevel.LOW,
        criticality=Criticality.C4,
        verdict_privileged=PolicyVerdict.ALLOW,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(privileged_role,),
        description=description,
    )


# gitlab git-family read actions (gitlab has no committed governance catalog).
EXTRA_SPECS: tuple[ActionSpec, ...] = (
    _read_spec("gitlab", "read_repo", "devops_admin", "Read a GitLab project (read-only)."),
    _read_spec("gitlab", "list_repos", "devops_admin", "List GitLab projects of a group."),
)

# All verdicts here come from the catalog baseline (allow-path reads above,
# committed-domain defaults for the rest); no contextual override needed.
EXTRA_RULES: tuple[tuple[str, str, str, PolicyVerdict, RiskLevel], ...] = ()


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
    # Only layer in the EXTRA_SPECS the committed catalog does not already define.
    # gitlab git-family reads live here because gitlab had no governance catalog;
    # if a committed gitlab domain later adds them, defer to it (no duplicate).
    base = tuple(load_catalog().all())
    known = {(s.target_system, s.action_type) for s in base}
    extra = tuple(s for s in EXTRA_SPECS if (s.target_system, s.action_type) not in known)
    return Catalog(base + extra)


def build_bundle(catalog: Catalog) -> PolicyVersion:
    base = baseline_from_catalog(catalog, version=BUNDLE_VERSION)
    extra = tuple(
        PolicyRule(
            rule_id=f"md.{target}.{action}.{role}",
            target_system=target,
            action_type=action,
            role=role,
            verdict=verdict,
            risk_level=risk,
        )
        for target, action, role, verdict, risk in EXTRA_RULES
    )
    return PolicyVersion(version=BUNDLE_VERSION, rules=base.rules + extra)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_multidomain_scenarios")
    parser.add_argument("--dir", default="campaigns/multidomain")
    args = parser.parse_args(argv)

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
        runner = CampaignRunner(cast(HttpClient, client))

        files = sorted(Path(args.dir).glob("*.campaign.json"))
        if not files:
            print(f"no campaign files in {args.dir}/", file=sys.stderr)
            return 1

        all_ok = True
        for path in files:
            doc = load_campaign(path)
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
            if not report.chain_ok:
                print("    audit chain: BROKEN")
            all_ok = all_ok and report.ok

        print(f"\n{'ALL PASS' if all_ok else 'FAILURES PRESENT'} -- {len(files)} campaigns")
        return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
