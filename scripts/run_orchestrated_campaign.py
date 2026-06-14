"""Run every macro orchestration campaign: a campaign linked to a MAF team.

The repo judges multi-agent behaviour in two complementary ways:

  * a MAF orchestration TEAM (corpus/maf_orchestration/) is judged on the four
    dimensions as a plan -- who hands off to whom, which gated tool is approved;
  * a CAMPAIGN (campaigns/) submits the same business action through the real
    gateway, where the Control Plane renders the binding verdict.

A "macro orchestration campaign" is a normal campaign that carries a ``links``
block naming a MAF team and the ``shared_action`` whose human gate (I6) both
sides must agree on. This harness is DATA-DRIVEN: it discovers those links from
the campaign files themselves (no hardcoded table). For each link it judges the
team, runs the campaign through an in-memory gateway, and asserts the shared
action escalates in the governed run -- the team PLANS the gate (approval=always
tool), the gateway ENFORCES it (escalate -> pending).

Deterministic: the team judgement is pure (no clock/random), the campaign runs
against an in-memory gateway with a stub proxy. No LLM, no network.

Usage: python3 scripts/run_orchestrated_campaign.py
Exit 0 iff every linked pair agrees (team verdict matches its ground-truth AND
the campaign verdicts match their expectations AND the shared action escalates).
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

# Allow `python scripts/run_orchestrated_campaign.py` (file run) to import the
# sibling harness as `scripts.run_multidomain_scenarios`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recette.api.app import create_app  # noqa: E402
from recette.api.config_store import ConfigStore  # noqa: E402
from recette.campaign import CampaignRunner, HttpClient, load_campaign  # noqa: E402
from recette.maf_orchestration import judge_orchestration, run_from_doc  # noqa: E402
from recette.manifest import load_validated  # noqa: E402
from recette.platform.eventstore.memory_store import InMemoryEventStore  # noqa: E402
from recette.platform.policy.store import PolicyStore  # noqa: E402
from scripts.run_multidomain_scenarios import (  # noqa: E402
    BUNDLE_VERSION,
    _StubProxy,
    build_bundle,
    build_extended_catalog,
)

CAMPAIGNS_DIR = Path("campaigns")
ORCH_CORPUS = Path("corpus/maf_orchestration")


@dataclass(frozen=True)
class MacroLink:
    """One declared (campaign -> MAF team) binding discovered from a campaign file."""

    campaign_name: str
    campaign_path: Path
    team: str
    team_dir: Path
    shared_action: str
    invariant: str
    note: str


def _team_dir(team: str) -> Path | None:
    """Resolve a MAF team subject id to its corpus directory (correct/ or incorrect/)."""
    for category in ("correct", "incorrect"):
        candidate = ORCH_CORPUS / category / team
        if (candidate / "team.json").exists():
            return candidate
    return None


def discover_links(campaigns_dir: Path = CAMPAIGNS_DIR) -> list[MacroLink]:
    """Scan campaign files for a ``links`` block and resolve each MAF team dir.
    Sorted by (campaign, team) for a stable, deterministic run order (I4)."""
    found: list[MacroLink] = []
    for path in sorted(campaigns_dir.rglob("*.campaign.json")):
        doc = load_campaign(path)
        for link in doc.get("links", []):
            if link.get("kind") != "maf_orchestration":
                continue
            team = str(link["team"])
            team_dir = _team_dir(team)
            if team_dir is None:
                raise SystemExit(f"{path}: link team {team!r} has no corpus directory")
            found.append(
                MacroLink(
                    campaign_name=str(doc.get("name", path.stem)),
                    campaign_path=path,
                    team=team,
                    team_dir=team_dir,
                    shared_action=str(link["shared_action"]),
                    invariant=str(link.get("invariant", "")),
                    note=str(link.get("note", "")),
                )
            )
    found.sort(key=lambda m: (m.campaign_name, m.team))
    return found


def _team_verdict(team_dir: Path) -> tuple[str, str]:
    """Return (judged_verdict, expected_verdict) for a team directory."""
    team = load_validated("maf_orchestration", team_dir / "team.json")
    run_doc = load_validated("maf_orchestration_run", team_dir / "run.json")
    ground_truth = json.loads((team_dir / "ground-truth.json").read_text(encoding="utf-8"))
    result = judge_orchestration(team, run_from_doc(run_doc))
    return str(result.verdict), str(ground_truth["expected_verdict"])


def main(argv: list[str] | None = None) -> int:
    from fastapi.testclient import TestClient

    links = discover_links()
    if not links:
        print("no macro orchestration campaigns (no campaign carries a 'links' block)")
        return 1

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

        for link in links:
            team_judged, team_expected = _team_verdict(link.team_dir)
            team_ok = team_judged == team_expected

            report = runner.run(load_campaign(link.campaign_path))
            camp_ok = report.ok and report.chain_ok

            # The link assertion: the shared business action escalates in the
            # governed run (its declared approval gate is enforced by the gateway).
            gated = [
                r
                for r in report.results
                if r.action_type == link.shared_action and r.verdict == "escalate"
            ]
            link_ok = bool(gated)

            ok = team_ok and camp_ok and link_ok
            all_ok = all_ok and ok
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {link.campaign_name} <-> {link.team}")
            print(f"    team   {link.team}: judged={team_judged} expected={team_expected}")
            counts = ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items()) if v)
            print(f"    campaign {report.name}: {counts} chain_ok={report.chain_ok}")
            mark = "ok " if link_ok else "MISS"
            inv = f" [{link.invariant}]" if link.invariant else ""
            print(f"    {mark} link: {link.shared_action} escalates in the governed run{inv}")
            if link.note:
                print(f"         {link.note}")

        verdict = "ALL PASS" if all_ok else "FAILURES PRESENT"
        print(f"\n{verdict} -- {len(links)} macro orchestration campaigns")
        return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
