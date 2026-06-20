"""Discovery / surface / publish / bundle CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

from ..discovery_harness import (
    SURFACE_CORPUS,
    SURFACE_ORDER,
    discover_repo_dirs,
    run_discovery_recette,
)
from ._paths import _REPO_ROOT


def _build_source_adapter(adapter_name: str):
    """Return a fresh SourceScanAdapter for one surface run (None = reference oracle)."""
    if adapter_name == "reference":
        return None  # harness default = ReferenceSourceScanAdapter
    if adapter_name == "http":
        from ..http_adapter import HttpSourceScanAdapter

        return HttpSourceScanAdapter()
    raise ValueError(f"unknown adapter {adapter_name}")


def _cmd_discovery(adapter_name: str, surface: str) -> int:
    try:
        _build_source_adapter(adapter_name)  # validate adapter name early
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if surface == "all":
        surfaces = [s for s in SURFACE_ORDER if discover_repo_dirs(SURFACE_CORPUS[s])]
    else:
        surfaces = [surface]

    all_ok = True
    for s in surfaces:
        scorecard = run_discovery_recette(
            _build_source_adapter(adapter_name), corpus_root=SURFACE_CORPUS[s]
        )
        print(f"--- surface: {s} ---")
        print(scorecard.render())
        all_ok = all_ok and scorecard.all_passed
    if not surfaces:
        print("no discovery corpus found for the requested surface", file=sys.stderr)
        return 1
    return 0 if all_ok else 1


def _cmd_surface(recording: str | None = None) -> int:
    """Run the per-surface detection recette, print the scorecard.

    Proves the discovery probe SEES each simulated agent on each observation surface
    (subprocess/MCP/SDK hooks + eBPF/wire). With ``--recording`` it scores a
    discoveryprobe broker capture (a live eBPF capture frozen to JSON) through the
    SAME judge; without it, the in-bench corpus projection. Exit 1 if any agent is
    detected on no surface (the thesis failure). Design:
    docs/plans/2026-06-16-discoveryprobe-ebpf-reference-probe-design.md (sec. 12.4).
    """
    import json
    from dataclasses import asdict

    if recording is not None:
        from ..surface.recording import score_recording

        card = score_recording(Path(recording).read_text(encoding="utf-8"))
        print(json.dumps(asdict(card), sort_keys=True, indent=2))
        return 0 if card.ok else 1

    from ..surface.summary import surface_corpus_scorecard

    card = surface_corpus_scorecard()
    print(json.dumps(asdict(card), sort_keys=True, indent=2))
    return 0 if card.ok else 1


def _cmd_publish(slug: str, owner: str, visibility: str, apply: bool) -> int:
    from ..publish import publish_repo

    plan = publish_repo(slug, owner, visibility=visibility, dry_run=not apply)
    print(plan.render())
    if not apply:
        print("\n(dry-run -- nothing created. Re-run with --apply to create the repo.)")
    return 0


def _cmd_bundle_verify(path: str, pubkey: str | None) -> int:
    from ..bundle import verify_bundle_file

    schema_path = _REPO_ROOT / "corpus" / "schemas" / "policy-bundle.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    shape_errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(bundle), key=str)
    if shape_errors:
        for err in shape_errors:
            print(f"INVALID bundle shape: {err.message}", file=sys.stderr)
        return 1

    result = verify_bundle_file(path, expected_public_key=pubkey)
    print(f"bundle: {path}")
    print(f"verdict: {'VALID' if result.valid else 'INVALID'} -- {result.reason}")
    return 0 if result.valid else 1


def _cmd_receipts_verify(path: str, pubkey: str | None, as_json: bool) -> int:
    """Verify a signed context-receipt export off-platform (file + public key only).

    The terminal twin of POST /proxy/receipts/verify-import: checks the Ed25519
    signature over the canonical payload AND the receipt hash chain, trusting
    nothing in the envelope. Pure given the file (I4). Exit 0 only when BOTH the
    signature is valid and the chain is intact -- a third party (auditor, RSSI)
    proves the trail without the platform, the console, or a network call."""
    from ..context_receipt import verify_chain
    from ..receipt_export import verify_export

    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(envelope, dict):
        print("INVALID export: top level is not an envelope object", file=sys.stderr)
        return 1
    signature = verify_export(envelope, expected_public_key=pubkey)
    receipts = envelope.get("receipts")
    chain = verify_chain(receipts if isinstance(receipts, list) else [])
    ok = bool(signature["valid"]) and bool(chain["ok"])
    if as_json:
        print(json.dumps({"signature": signature, "chain": chain, "ok": ok}, indent=2))
        return 0 if ok else 1
    print(f"export: {path}")
    print(f"signature: {'VALID' if signature['valid'] else 'INVALID'} -- {signature['reason']}")
    if chain["ok"]:
        print(f"chain: INTACT -- {chain['checked']} receipt(s)")
    else:
        print(f"chain: BROKEN -- first break at seq {chain['first_break_seq']}")
    print(f"verdict: {'VALID' if ok else 'INVALID'}")
    return 0 if ok else 1
