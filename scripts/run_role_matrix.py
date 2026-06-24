"""Run the role x action matrix campaigns through the real gateway and check verdicts.

No LLM, no network: every action flows through the genuine policy decide ->
deny / escalate / allow path over the COMMITTED catalog and the baseline policy
(one rule per privileged role, every other (action, role) falling through to
deny-by-default). This proves that for each defined role and each catalogued
action the engine returns exactly ActionSpec.verdict_for_role(role) -- the
role-specific posture, including capability_overreach denial.

Unlike run_banque_scenarios.py this harness adds NO extra specs and NO contextual
grant bundle: it validates the committed governance posture as shipped.

Usage: python3 scripts/run_role_matrix.py [--dir campaigns/role-matrix]
Exit code 0 if every campaign matches its expectations and the audit chain is
intact, 1 otherwise.
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
from recette.platform.catalog import load_catalog
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.policy.model import baseline_from_catalog
from recette.platform.policy.store import PolicyStore
from recette.platform.proxy.protocol import ExecutionResult, side_effect_hash

BUNDLE_VERSION = "baseline-v1"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_role_matrix")
    parser.add_argument("--dir", default="campaigns/role-matrix")
    args = parser.parse_args(argv)

    from fastapi.testclient import TestClient

    catalog = load_catalog()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        policies = PolicyStore(tmp / "policies")
        policies.publish(baseline_from_catalog(catalog, version=BUNDLE_VERSION))
        policies.set_active(BUNDLE_VERSION)
        app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=policies,
            proxy=_StubProxy(),
            catalog=catalog,
        )
        client = TestClient(app)
        # TestClient.post carries extra httpx kwargs so it is not structurally a
        # HttpClient; the runner only uses the shared (path, json=...) subset.
        runner = CampaignRunner(cast(HttpClient, client))

        files = sorted(Path(args.dir).glob("*.campaign.json"))
        if not files:
            print(f"no campaign files in {args.dir}/", file=sys.stderr)
            return 1

        all_ok = True
        total_actions = total_miss = 0
        for path in files:
            doc = load_campaign(path)
            report = runner.run(doc)
            status = "PASS" if report.ok else "FAIL"
            counts = ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items()) if v)
            misses = [r for r in report.results if not r.matches_expectation]
            total_actions += len(report.results)
            total_miss += len(misses)
            print(f"[{status}] {report.name}  ({counts})")
            for r in misses:
                print(
                    f"    MISS {r.target_system}/{r.action_type} -> "
                    f"{r.verdict}/{r.approval_state}  expected={r.expected_verdict}"
                )
            if not report.chain_ok:
                print("    audit chain: BROKEN")
            all_ok = all_ok and report.ok

        print(
            f"\n{'ALL PASS' if all_ok else 'FAILURES PRESENT'} -- {len(files)} campaigns, "
            f"{total_actions} (role, action) pairs, {total_miss} mismatches"
        )
        return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
