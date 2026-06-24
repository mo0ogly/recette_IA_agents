"""Campaign runner: submit a scripted batch of governed actions through the API.

A campaign is a JSON document (see campaigns/*.campaign.json) declaring the
agents to seed and the ordered actions to submit through the gateway. Every
action flows through the full governed path (policy decide -> deny / escalate
-> pending / allow -> execute), so a campaign produces a real audit trail and
a real approval inbox -- nothing is bypassed (I2).

Optional per-action "expect" assertions turn a campaign into a checkable
scenario: the runner exits non-zero on any verdict mismatch, making campaigns
usable both as demo seeders for the console and as black-box recette runs.

Like the orchestration teams and Lane B agents, a campaign run is replayable: a
CampaignRecording captures the verdict sequence, and replaying re-submits the
same document and asserts the verdicts reproduce (I4 at the campaign level).

CLI:
  python -m recette.campaign list [--dir campaigns]
  python -m recette.campaign run <file> [--api URL] [--json out.json]
  python -m recette.campaign record <file> --out rec.json [--api URL]
  python -m recette.campaign replay <recording> [--api URL]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DEFAULT_API_URL = "http://127.0.0.1:8090"
DEFAULT_CAMPAIGNS_DIR = "campaigns"


class CampaignError(ValueError):
    """Raised on a malformed campaign document."""


class HttpClient(Protocol):
    """Minimal client surface (StdlibHttpClient and FastAPI TestClient adapters fit)."""

    def post(self, path: str, json: dict | None = None) -> object: ...
    def get(self, path: str) -> object: ...


@dataclass(frozen=True)
class ActionResult:
    index: int
    agent_id: str
    target_system: str
    action_type: str
    resource: str
    verdict: str
    approval_state: str
    executed: bool
    event_id: str
    side_effect_hash: str | None
    expected_verdict: str | None
    matches_expectation: bool
    rationale: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "agent_id": self.agent_id,
            "target_system": self.target_system,
            "action_type": self.action_type,
            "resource": self.resource,
            "verdict": self.verdict,
            "approval_state": self.approval_state,
            "executed": self.executed,
            "event_id": self.event_id,
            "side_effect_hash": self.side_effect_hash,
            "expected_verdict": self.expected_verdict,
            "matches_expectation": self.matches_expectation,
            "rationale": self.rationale,
        }


@dataclass
class CampaignReport:
    name: str
    results: list[ActionResult] = field(default_factory=list)
    chain_ok: bool | None = None
    chain_checked: int | None = None
    objective: str | None = None
    teaching: str | None = None

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {"allow": 0, "deny": 0, "escalate": 0}
        for r in self.results:
            out[r.verdict] = out.get(r.verdict, 0) + 1
        return out

    @property
    def pending_event_ids(self) -> list[str]:
        return [r.event_id for r in self.results if r.approval_state == "pending"]

    @property
    def mismatches(self) -> list[ActionResult]:
        return [r for r in self.results if not r.matches_expectation]

    @property
    def ok(self) -> bool:
        return not self.mismatches and self.chain_ok is not False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "objective": self.objective,
            "teaching": self.teaching,
            "ok": self.ok,
            "counts": self.counts,
            "pending_event_ids": self.pending_event_ids,
            "mismatch_count": len(self.mismatches),
            "chain_ok": self.chain_ok,
            "chain_checked": self.chain_checked,
            "results": [r.to_dict() for r in self.results],
        }


# Campaign kinds. A CATALOG PROBE (coverage-* / role-matrix-*) exhaustively
# exposes a system's or role's whole action set -- it is a COVERAGE instrument,
# not an adversarial narrative. Scorers must EXCLUDE it from the adversarial
# resistance signal (a catalog probe that touches a deny action is not a jailbreak,
# it is the probe doing its job). This is a HARD tag carried in the campaign JSON
# (`"kind": "catalog_probe"`), so the exclusion is by construction -- not a fragile
# name-prefix heuristic (#8).
_CAMPAIGN_KINDS = frozenset({"catalog_probe"})


def is_catalog_probe(doc: dict) -> bool:
    """True if a campaign is a catalog/role-matrix coverage probe (hard tag)."""
    return doc.get("kind") == "catalog_probe"


def validate_campaign(doc: dict) -> None:
    """Structural validation -- fail fast before touching the API."""
    if not isinstance(doc.get("name"), str) or not doc["name"]:
        raise CampaignError("campaign needs a non-empty 'name'")
    kind = doc.get("kind")
    if kind is not None and kind not in _CAMPAIGN_KINDS:
        raise CampaignError(
            f"unknown campaign 'kind': {kind!r} (allowed: {sorted(_CAMPAIGN_KINDS)})"
        )
    # Optional teaching fields (pure documentation, never reach the decision path).
    for key in ("objective", "teaching"):
        if key in doc and not isinstance(doc[key], str):
            raise CampaignError(f"'{key}' must be a string when present")
    agents = doc.get("agents", [])
    if not isinstance(agents, list):
        raise CampaignError("'agents' must be a list")
    for agent in agents:
        if not isinstance(agent, dict) or "id" not in agent or "runtime" not in agent:
            raise CampaignError("each agent needs at least 'id' and 'runtime'")
    actions = doc.get("actions")
    if not isinstance(actions, list) or not actions:
        raise CampaignError("'actions' must be a non-empty list")
    required = {"agent_id", "target_system", "action_type", "resource"}
    for i, action in enumerate(actions):
        if not isinstance(action, dict) or not required.issubset(action):
            raise CampaignError(f"action #{i} must carry {sorted(required)}")
        expect = action.get("expect")
        if expect is not None and expect not in {"allow", "deny", "escalate"}:
            raise CampaignError(f"action #{i}: expect must be allow|deny|escalate")
        rationale = action.get("rationale")
        if rationale is not None and not isinstance(rationale, str):
            raise CampaignError(f"action #{i}: 'rationale' must be a string when present")
    _validate_links(doc)


def _validate_links(doc: dict) -> None:
    """A macro orchestration campaign may carry ``links``: declared bindings to a
    MAF orchestration team it agrees with on a governed action. Each link names
    the team (corpus/maf_orchestration subject id) and the shared action_type
    whose human gate (I6) both the team's tool approval and the campaign's
    gateway verdict must agree on. Pure documentation + harness wiring; it never
    reaches the decision path, so it cannot threaten replay determinism (I4)."""
    links = doc.get("links")
    if links is None:
        return
    if not isinstance(links, list):
        raise CampaignError("'links' must be a list when present")
    for i, link in enumerate(links):
        if not isinstance(link, dict):
            raise CampaignError(f"link #{i} must be an object")
        for key in ("kind", "team", "shared_action"):
            if not isinstance(link.get(key), str) or not link[key]:
                raise CampaignError(f"link #{i} needs a non-empty '{key}' string")
        if link["kind"] != "maf_orchestration":
            raise CampaignError(f"link #{i}: only kind 'maf_orchestration' is supported")
        for key in ("invariant", "note"):
            if key in link and not isinstance(link[key], str):
                raise CampaignError(f"link #{i}: '{key}' must be a string when present")


def load_campaign(path: Path | str) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_campaign(doc)
    return doc


class CampaignRunner:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def _seed_agents(self, agents: list[dict]) -> None:
        for agent in agents:
            resp = self._client.post("/config/agents", json=agent)
            status = int(getattr(resp, "status", 0) or getattr(resp, "status_code", 0) or 0)
            # 400 "already exists" is fine on reruns; anything else >= 400 is not.
            if status >= 400 and status != 400:
                raise CampaignError(f"seeding agent {agent['id']!r} failed: HTTP {status}")

    def run(self, doc: dict) -> CampaignReport:
        validate_campaign(doc)
        report = CampaignReport(
            name=doc["name"],
            objective=doc.get("objective"),
            teaching=doc.get("teaching"),
        )
        self._seed_agents(doc.get("agents", []))
        for i, action in enumerate(doc["actions"]):
            body = {
                "agent_id": action["agent_id"],
                "target_system": action["target_system"],
                "action_type": action["action_type"],
                "resource": action["resource"],
                "payload": action.get("payload", {}),
            }
            resp = self._client.post("/actions/execute", json=body)
            outcome = resp.json()  # type: ignore[attr-defined]
            expected = action.get("expect")
            verdict = str(outcome.get("verdict", ""))
            report.results.append(
                ActionResult(
                    index=i,
                    agent_id=body["agent_id"],
                    target_system=body["target_system"],
                    action_type=body["action_type"],
                    resource=body["resource"],
                    verdict=verdict,
                    approval_state=str(outcome.get("approval_state", "")),
                    executed=bool(outcome.get("executed", False)),
                    event_id=str(outcome.get("event_id", "")),
                    side_effect_hash=outcome.get("side_effect_hash"),
                    expected_verdict=expected,
                    matches_expectation=(expected is None or verdict == expected),
                    rationale=action.get("rationale"),
                )
            )
        verify = self._client.get("/audit/verify").json()  # type: ignore[attr-defined]
        report.chain_ok = bool(verify.get("ok"))
        report.chain_checked = verify.get("checked")
        return report


def _verdict_rows(report: CampaignReport) -> list[dict]:
    """The verdict sequence of a run -- the comparable core of a recording."""
    return [
        {
            "index": r.index,
            "verdict": r.verdict,
            "approval_state": r.approval_state,
            "executed": r.executed,
        }
        for r in report.results
    ]


@dataclass
class CampaignRecording:
    """A persistent, replayable record of one campaign run (mirrors the
    orchestration/Lane B recordings). It stores the campaign document and the
    verdict sequence the gateway produced. Replaying re-submits the same document
    and asserts the verdicts reproduce -- the campaign-level I4 check ("rejouer
    pour voir si ca fait la meme chose")."""

    name: str
    doc: dict
    verdicts: list[dict] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "doc": self.doc,
            "verdicts": self.verdicts,
        }

    @staticmethod
    def from_dict(d: dict) -> CampaignRecording:
        return CampaignRecording(
            name=d["name"],
            doc=d["doc"],
            verdicts=d.get("verdicts", []),
            schema_version=d.get("schema_version", "1.0"),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> CampaignRecording:
        return CampaignRecording.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def record_campaign(runner: CampaignRunner, doc: dict) -> CampaignRecording:
    """Run the campaign through the gateway and capture its verdict sequence."""
    report = runner.run(doc)
    return CampaignRecording(name=doc["name"], doc=doc, verdicts=_verdict_rows(report))


def replay_campaign(
    runner: CampaignRunner, recording: CampaignRecording
) -> tuple[CampaignReport, bool]:
    """Re-submit the recorded campaign and report whether the verdicts reproduce.

    Returns (fresh report, deterministic). A True flag means the gateway produced
    the exact same verdict sequence as the recording (I4 at the campaign level)."""
    report = runner.run(recording.doc)
    deterministic = _verdict_rows(report) == recording.verdicts
    return report, deterministic


def _render_report(report: CampaignReport) -> str:
    lines = [f"campaign: {report.name}"]
    if report.objective:
        lines.append(f"objective: {report.objective}")
    lines.append(
        "verdicts: "
        + ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items()) if v or k != "allow")
    )
    for r in report.results:
        mark = "OK" if r.matches_expectation else "MISMATCH"
        suffix = f" expected={r.expected_verdict}" if not r.matches_expectation else ""
        lines.append(
            f"  [{mark}] #{r.index} {r.agent_id} {r.target_system}/{r.action_type}"
            f" -> {r.verdict}/{r.approval_state}{suffix}"
        )
        if r.rationale:
            lines.append(f"        why: {r.rationale}")
    if report.pending_event_ids:
        lines.append(f"pending approvals: {len(report.pending_event_ids)}")
        for event_id in report.pending_event_ids:
            lines.append(f"  {event_id}")
    lines.append(f"audit chain: {'intact' if report.chain_ok else 'BROKEN'}")
    if report.teaching:
        lines.append(f"teaching: {report.teaching}")
    lines.append(f"result: {'PASS' if report.ok else 'FAIL'}")
    return "\n".join(lines)


def _cmd_list(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    files = sorted(directory.rglob("*.campaign.json"))
    if not files:
        print(f"no campaign files in {directory}/")
        return 0
    for path in files:
        rel = path.relative_to(directory)
        try:
            doc = load_campaign(path)
            print(f"{rel}: {doc['name']} ({len(doc['actions'])} actions)")
            if doc.get("objective"):
                print(f"    {doc['objective']}")
        except (CampaignError, json.JSONDecodeError) as exc:
            print(f"{rel}: INVALID ({exc})")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from ._http_client import StdlibHttpClient

    doc = load_campaign(args.file)
    client = StdlibHttpClient(args.api)
    report = CampaignRunner(client).run(doc)
    print(_render_report(report))
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", "utf-8")
        print(f"report written: {out}")
    return 0 if report.ok else 1


def _cmd_record(args: argparse.Namespace) -> int:
    from ._http_client import StdlibHttpClient

    doc = load_campaign(args.file)
    recording = record_campaign(CampaignRunner(StdlibHttpClient(args.api)), doc)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    recording.save(out)
    print(f"recorded {len(recording.verdicts)} verdicts; recording written: {out}")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    from ._http_client import StdlibHttpClient

    recording = CampaignRecording.load(args.recording)
    report, deterministic = replay_campaign(CampaignRunner(StdlibHttpClient(args.api)), recording)
    print(_render_report(report))
    print(f"replay deterministic: {deterministic}")
    return 0 if (deterministic and report.ok) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recette.campaign")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list campaign files")
    p_list.add_argument("--dir", default=DEFAULT_CAMPAIGNS_DIR)
    p_list.set_defaults(func=_cmd_list)

    p_run = sub.add_parser("run", help="run a campaign against the API")
    p_run.add_argument("file")
    p_run.add_argument(
        "--api", default=os.environ.get("INSPECT_IA_AGENTS_API_URL", DEFAULT_API_URL)
    )
    p_run.add_argument("--json", default=None, help="write the full report to this path")
    p_run.set_defaults(func=_cmd_run)

    p_rec = sub.add_parser("record", help="run a campaign and save a replayable recording")
    p_rec.add_argument("file")
    p_rec.add_argument(
        "--api", default=os.environ.get("INSPECT_IA_AGENTS_API_URL", DEFAULT_API_URL)
    )
    p_rec.add_argument("--out", required=True, help="recording output path")
    p_rec.set_defaults(func=_cmd_record)

    p_rep = sub.add_parser("replay", help="replay a recording and check verdicts reproduce (I4)")
    p_rep.add_argument("recording")
    p_rep.add_argument(
        "--api", default=os.environ.get("INSPECT_IA_AGENTS_API_URL", DEFAULT_API_URL)
    )
    p_rep.set_defaults(func=_cmd_replay)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (CampaignError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
