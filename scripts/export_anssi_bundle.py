"""Export an ANSSI-researcher bundle: every surface log + the scorecard, made
tamper-evident and REPLAYABLE.

The recette is built to be reproduced, not just read: the deterministic pass is
byte-stable (I4), and the live SKYNET runs are RECORDED, so a researcher replays
them with ReplayLlm and recomputes the same scorecard (the scorer is a pure
function of the logs). This packages, for one LLM run:

  logs/        -- all per-surface captures (agents / traced / campaigns / surface / redteam)
  scorecard.json -- the governance scorecard (stars + detailed /100), recomputable
  MANIFEST.json -- sha256 of every file + a chained root hash (tamper-evident, I1
                   style) + the git commit, the LLM id, and the replay recipe
  README.md    -- how to analyze and how to replay

Integrity is a hash chain (each entry hashes the previous root + this file's
digest), so any altered byte changes the root -- a researcher verifies the bundle
before trusting it. Pure over its inputs except the file bytes it reads.

Run: python3 scripts/export_anssi_bundle.py --llm skynet/gpt-oss-120b [--out <dir>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_REC = _ROOT / "docs" / "tracking" / "recette"

_SURFACE_LOGS = [
    "agents_live_skynet.jsonl",
    "traced_skynet.jsonl",
    "campaigns_live_skynet.jsonl",
    "jailbreak_threshold_skynet.jsonl",
    "discovery_vs_proxy_skynet.json",
    "seen_vs_done_skynet.json",
    "surface.json",
    "ebpf_live_skynet.json",
    "probe_audit_skynet.jsonl",
    "proxy_traces_skynet.jsonl",
    "redteam_ok.txt",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _chain(entries: list[dict]) -> str:
    """Tamper-evident root: fold each file digest into a running hash (I1 style)."""
    root = "0" * 64
    for e in sorted(entries, key=lambda x: x["file"]):
        root = hashlib.sha256(f"{root}{e['sha256']}".encode()).hexdigest()
    return root


def build(llm: str, out_dir: Path) -> dict:
    """Assemble the bundle dir and return the MANIFEST. Idempotent for a fixed input."""
    logs = out_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    for name in _SURFACE_LOGS:
        src = _REC / name
        if not src.exists():
            continue
        dst = logs / name
        dst.write_bytes(src.read_bytes())
        entries.append({"file": f"logs/{name}", "sha256": _sha256(dst)})

    # The scorecard, recomputed here so the bundle is self-contained.
    from recette_govscore import score  # local import; scripts/ on sys.path via runner

    scorecard = score(_REC, llm)
    sc_path = out_dir / "scorecard.json"
    sc_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    entries.append({"file": "scorecard.json", "sha256": _sha256(sc_path)})

    manifest = {
        "llm": llm,
        "git_commit": _git_sha(),
        "files": entries,
        "root_hash": _chain(entries),
        "replay": {
            "deterministic_recette": "python3 scripts/recette_full.py  (byte-stable, I4)",
            "live_runs": "recorded; replay with `python3 -m recette agent replay <recording>` "
            "(ReplayLlm reproduces the SKYNET decisions deterministically)",
            "recompute_scorecard": f"python3 scripts/recette_govscore.py --llm {llm} --json",
            "verify_integrity": "recompute sha256 of each logs/* + scorecard.json, re-fold "
            "into root_hash; it must match.",
        },
        "schema": "anssi-recette-bundle/v1",
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme = f"""# ANSSI recette bundle -- {llm}

Tamper-evident, replayable capture of an inspect_ia_agents governance recette.

## Contents
- `logs/` -- every surface: declared/decided (agents), done/proxy (traced
  summary), campaigns, jailbreak threshold, discovery-vs-proxy agreement, eBPF
  surface (`surface.json` = deterministic corpus projection; `ebpf_live_skynet.json`
  = REAL per-PID live captures under the CAP_BPF broker, with
  `probe_audit_skynet.jsonl` the broker's tamper-evident seq+sha256 audit chain),
  red-team.
- `logs/proxy_traces_skynet.jsonl` -- THE RAW PROXY LOG: one line per side
  effect, the full agent<->server exchange (`request_payload` = the intent,
  `response` = what the target system answered, `side_effect_hash`, `event_id`,
  `timestamp`, `run_id`). This is the legibility-first "what it DID" surface and
  the ground truth a researcher replays the exchange against -- not a summary.
- `scorecard.json` -- governance stars + detailed /100 (L1/L2/L3), per-server
  improvement ranking, cross-surface consistency.
- `MANIFEST.json` -- sha256 of every file + a chained `root_hash` + the git commit
  + the replay recipe.

## Verify integrity
Recompute the sha256 of each file in `logs/` and `scorecard.json`, fold them into
`root_hash` (sorted by path: root = sha256(root + digest)); it must equal
`MANIFEST.root_hash`. Any altered byte changes the root.

## Replay
- Deterministic recette: `python3 scripts/recette_full.py` -- byte-stable (I4).
- Live runs: recorded; `python3 -m recette agent replay <recording>` reproduces the
  LLM decisions via ReplayLlm (no live call, no key).
- Proxy exchange: `logs/proxy_traces_skynet.jsonl` holds the full request+response
  per side effect. The mock lab is deterministic (I4): the SAME
  (agent, action_type, resource) request always yields the SAME response and
  `side_effect_hash` -- verified across two independent live passes (46/46
  side_effect_hash matched). So to replay the exchange, replay the LLM DECISIONS
  via ReplayLlm (`recette agent replay <recording>`) to fix the requests; every
  response + `side_effect_hash` then reproduces byte-for-byte. The hash is the
  exchange's fingerprint -- equal hash = equal effect. (A fresh LIVE LLM may
  decide different requests, so re-running with a live brain is NOT a byte replay;
  only the recorded-decision path is, R14.)
- Recompute the scorecard: `python3 scripts/recette_govscore.py --llm {llm} --json`
  -- the score is a pure function of the logs, so it matches.

git commit: {manifest["git_commit"]}
root_hash: {manifest["root_hash"]}
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def _register_bundle(llm: str, out_dir: Path, manifest: dict, eurodate: str) -> None:
    """Register the bundle as a sealed run-group so it is browsable in the Runs
    Explorer (web-only researcher surface). Fail-safe: a registry error never
    aborts the export. The bundle keeps its OWN MANIFEST root_hash; this just
    surfaces the integrity proof + scorecard + readme through the registry."""
    repo_root = str(_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from recette.runs.capture import capture_surface, update_latest_symlink
    except ImportError as exc:  # registry optional -- never fatal
        print(f"[anssi] registry capture unavailable (non-fatal): {exc}")
        return

    slug = llm.replace("/", "_")
    artifacts: dict[str, str] = {}
    for name in ("MANIFEST.json", "scorecard.json", "README.md"):
        path = out_dir / name
        if path.exists():
            artifacts[name] = path.read_text(encoding="utf-8")
    group_id = f"anssi-{slug}"
    capture_surface(
        category="anssi",
        group_id=group_id,
        eurodate=eurodate,
        label=f"ANSSI bundle {llm} (root {manifest['root_hash'][:12]})",
        runs={"bundle": {"kind": "anssi-bundle", "artifacts": artifacts}},
    )
    update_latest_symlink("anssi", eurodate, group_id)
    print(f"[anssi] registered in run-registry: anssi/{eurodate}_{group_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Export an ANSSI-researcher recette bundle.")
    ap.add_argument("--llm", default="skynet/gpt-oss-120b")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    slug = args.llm.replace("/", "_")
    out_dir = Path(args.out) if args.out else (_REC / f"anssi_bundle_{slug}")
    manifest = build(args.llm, out_dir)
    print(f"bundle: {out_dir}")
    print(f"files: {len(manifest['files'])} | root_hash: {manifest['root_hash'][:16]}...")
    print(f"git: {manifest['git_commit'][:12]} | llm: {manifest['llm']}")
    # Operational eurodate (wall clock) -- bundle export is an ops action, not a
    # decision/judge path (maf-standard rule); the registry itself stays clock-free.
    eurodate = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")  # noqa: DTZ005
    _register_bundle(args.llm, out_dir, manifest, eurodate)
    return 0


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
