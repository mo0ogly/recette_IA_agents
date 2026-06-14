"""Link a MAF orchestration team to its governed campaign (the two recettes joined).

The repo judges multi-agent behaviour in two complementary ways:

  * a MAF orchestration TEAM (corpus/maf_orchestration/) is judged on the four
    dimensions as a plan -- who hands off to whom, which gated tool is approved;
  * a CAMPAIGN (campaigns/) submits the same business action through the real
    gateway, where the Control Plane renders the binding verdict.

This harness asserts both halves of one scenario AGREE on where the human gate
sits. For finance-approval: the MAF team declares an approval=always MCP wire
tool and the run approves it (team verdict = correct); the governed campaign
submits the same launch_wire_transfer and the gateway escalates it to pending
(I6). The team PLANS the gate, the gateway ENFORCES it -- the link is that the
same business action is approval-bound on both sides.

Deterministic: the team judgement is pure (no clock/random), the campaign runs
against an in-memory gateway with a stub proxy. No LLM, no network.

Usage: python3 scripts/run_orchestrated_campaign.py
Exit 0 iff every linked pair agrees (team verdict matches its ground-truth AND
the campaign verdicts match their expectations AND the audit chain is intact).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from recette.api.app import create_app
from recette.api.config_store import ConfigStore
from recette.campaign import CampaignRunner, HttpClient, load_campaign
from recette.maf_orchestration import judge_orchestration, run_from_doc
from recette.manifest import load_validated
from recette.platform.eventstore.memory_store import InMemoryEventStore
from recette.platform.policy.store import PolicyStore
from scripts.run_multidomain_scenarios import (
    BUNDLE_VERSION,
    _StubProxy,
    build_bundle,
    build_extended_catalog,
)

CORPUS = Path("corpus/maf_orchestration")


@dataclass(frozen=True)
class Link:
    """One scenario expressed as a (judged team, governed campaign) pair."""

    name: str
    team_dir: Path
    campaign: Path
    business_action: str  # the action both sides agree is approval-bound
    note: str


LINKS: tuple[Link, ...] = (
    Link(
        name="finance-approval",
        team_dir=CORPUS / "correct" / "finance-approval-handoff-correct",
        campaign=Path("campaigns/multidomain/finance-approval-bridge.campaign.json"),
        business_action="launch_wire_transfer",
        note=(
            "MAF team declares approval=always on the wire MCP tool and approves it "
            "-> the gateway escalates launch_wire_transfer to pending (I6)."
        ),
    ),
)


def _team_verdict(team_dir: Path) -> tuple[str, str]:
    """Return (judged_verdict, expected_verdict) for a team directory."""
    team = load_validated("maf_orchestration", team_dir / "team.json")
    run_doc = load_validated("maf_orchestration_run", team_dir / "run.json")
    ground_truth = json.loads((team_dir / "ground-truth.json").read_text(encoding="utf-8"))
    result = judge_orchestration(team, run_from_doc(run_doc))
    return str(result.verdict), str(ground_truth["expected_verdict"])


def main(argv: list[str] | None = None) -> int:
    from fastapi.testclient import TestClient

    catalog = build_extended_catalog()
    all_ok = True
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

        for link in LINKS:
            team_judged, team_expected = _team_verdict(link.team_dir)
            team_ok = team_judged == team_expected

            report = runner.run(load_campaign(link.campaign))
            camp_ok = report.ok and report.chain_ok

            # The link assertion: the shared business action escalates in the
            # governed run (its declared approval gate is enforced by the gateway).
            gated = [
                r
                for r in report.results
                if r.action_type == link.business_action and r.verdict == "escalate"
            ]
            link_ok = bool(gated)

            ok = team_ok and camp_ok and link_ok
            all_ok = all_ok and ok
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {link.name}")
            print(f"    team   {link.team_dir.name}: judged={team_judged} expected={team_expected}")
            counts = ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items()) if v)
            print(f"    campaign {report.name}: {counts} chain_ok={report.chain_ok}")
            mark = "ok " if link_ok else "MISS"
            print(f"    {mark} link: {link.business_action} escalates in the governed run")
            print(f"         {link.note}")

        print(f"\n{'ALL PASS' if all_ok else 'FAILURES PRESENT'} -- {len(LINKS)} linked scenarios")
        return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
