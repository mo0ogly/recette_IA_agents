"""CLI entrypoint: python -m recette validate | run | discovery | ...

The command handlers were split by domain into the ``recette.cli`` package; this
module keeps the public surface (``build_parser``, ``main``, ``_cmd_surface``)
so ``python -m recette`` and the tests importing ``recette.__main__`` are
unchanged. ``main`` only parses args and dispatches to the grouped handlers.
"""

from __future__ import annotations

from .cli.agent_cmds import _cmd_agent_freeze, _cmd_agent_replay, _cmd_agent_run
from .cli.behavior_cmds import (
    _cmd_analyze_ablate,
    _cmd_analyze_export,
    _cmd_analyze_metrics,
    _cmd_analyze_replay,
    _cmd_analyze_sweep,
    _cmd_analyze_wave,
)
from .cli.corpus_cmds import (
    _cmd_benchmark,
    _cmd_import_maf,
    _cmd_maf,
    _cmd_report,
    _cmd_run,
    _cmd_validate,
)
from .cli.discovery_cmds import (
    _cmd_bundle_verify,
    _cmd_discovery,
    _cmd_publish,
    _cmd_receipts_attest,
    _cmd_receipts_verify,
    _cmd_surface,
)
from .cli.orchestrate_cmds import (
    _cmd_orchestrate_freeze,
    _cmd_orchestrate_otel,
    _cmd_orchestrate_replay,
    _cmd_orchestrate_run,
    _cmd_orchestrate_viz,
)
from .cli.parser import build_parser
from .cli.rag_cmds import _cmd_rag, _cmd_rag_kb
from .cli.redteam_cmds import _cmd_redteam, _cmd_redteam_promote, _cmd_redteam_record

__all__ = ["build_parser", "main", "_cmd_surface"]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _cmd_validate(args.corpus)
    if args.command == "run":
        return _cmd_run(args.corpus)
    if args.command == "rag":
        return _cmd_rag(args.eval, args.k)
    if args.command == "rag-kb":
        return _cmd_rag_kb(args.action, args.doc, args.doc_id, args.scenario)
    if args.command == "discovery":
        return _cmd_discovery(args.adapter, args.surface)
    if args.command == "report":
        return _cmd_report(args.json)
    if args.command == "bundle-verify":
        return _cmd_bundle_verify(args.path, args.pubkey)
    if args.command == "receipts-verify":
        return _cmd_receipts_verify(args.path, args.pubkey, args.json)
    if args.command == "receipts-attest":
        return _cmd_receipts_attest(args.attestation, args.proof, args.pubkey, args.json)
    if args.command == "agent":
        if args.agent_cmd == "run":
            return _cmd_agent_run(
                args.manifest,
                args.provider,
                args.model,
                args.max_steps,
                args.real,
                args.enable_writes,
                args.base_url,
            )
        if args.agent_cmd == "replay":
            return _cmd_agent_replay(args.recording)
        if args.agent_cmd == "freeze":
            return _cmd_agent_freeze(args.recording, args.out)
    if args.command == "orchestrate":
        if args.orch_cmd == "run":
            return _cmd_orchestrate_run(
                args.team,
                args.provider,
                args.model,
                args.base_url,
                args.max_steps,
                args.out,
                args.cache,
            )
        if args.orch_cmd == "replay":
            return _cmd_orchestrate_replay(args.recording)
        if args.orch_cmd == "otel":
            return _cmd_orchestrate_otel(args.recording, args.out)
        if args.orch_cmd == "viz":
            return _cmd_orchestrate_viz(args.target, args.run)
        if args.orch_cmd == "freeze":
            return _cmd_orchestrate_freeze(
                args.recording, args.out, args.slug, args.category, args.violation_type
            )
    if args.command == "maf":
        return _cmd_maf()
    if args.command == "benchmark":
        return _cmd_benchmark(args.json)
    if args.command == "import-maf":
        return _cmd_import_maf(args.spec, args.out)
    if args.command == "surface":
        return _cmd_surface(args.recording)
    if args.command == "analyze":
        if args.analyze_cmd == "wave":
            return _cmd_analyze_wave(args.evidence, args.profile, args.threat, args.json)
        if args.analyze_cmd == "replay":
            return _cmd_analyze_replay(args.evidence, args.profile, args.threat, args.report)
        if args.analyze_cmd == "metrics":
            return _cmd_analyze_metrics(args.evidence, args.profile, args.threat, args.json)
        if args.analyze_cmd == "sweep":
            return _cmd_analyze_sweep(
                args.evidence, args.profile, args.threat, args.knob, args.values
            )
        if args.analyze_cmd == "ablate":
            return _cmd_analyze_ablate(args.evidence, args.profile, args.threat)
        if args.analyze_cmd == "export":
            return _cmd_analyze_export(args.evidence, args.profile, args.threat, args.out)
    if args.command == "redteam":
        return _cmd_redteam()
    if args.command == "redteam-promote":
        return _cmd_redteam_promote(args.scenario_id, args.out, args.overwrite)
    if args.command == "redteam-record":
        return _cmd_redteam_record(args)
    if args.command == "publish":
        return _cmd_publish(args.slug, args.owner, args.visibility, args.apply)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
