"""Multi-agent orchestration CLI commands: run / replay / viz / otel / freeze."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _cmd_orchestrate_run(
    team_path: str,
    provider: str,
    model: str,
    base_url: str | None,
    max_steps: int,
    out: str | None,
    cache: str | None,
) -> int:
    from ..llm import LlmBackend, build_llm
    from ..maf_orchestration import judge_orchestration
    from ..manifest import load_validated
    from ..orchestrate import record

    try:
        llm: LlmBackend = build_llm(provider, model, base_url=base_url)  # live; key from env (R8)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if cache is not None:
        from ..llm_cache import CachingLlm, LlmCache

        llm = CachingLlm(llm, cache=LlmCache(cache), namespace=f"{provider}:{model}")
    team = load_validated("maf_orchestration", Path(team_path))
    rec = record(team, llm, provider=provider, model=model, max_steps=max_steps)
    out_path = Path(out or f"{team['agent_id']}.orchestration.json")
    rec.save(out_path)
    verdict = judge_orchestration(team, rec.run).verdict
    print(f"recorded {len(rec.decisions)} decisions; verdict={verdict}; saved {out_path}")
    return 0


def _cmd_orchestrate_replay(recording_path: str) -> int:
    from ..orchestrate import OrchestrationRecording, replay

    rec = OrchestrationRecording.load(recording_path)
    try:
        _, result = replay(rec)
    except ValueError as exc:
        print(f"replay diverged: {exc}", file=sys.stderr)
        return 1
    print(f"replay deterministic: True; verdict={result.verdict}")
    return 0


def _cmd_orchestrate_viz(target: str, from_run: bool) -> int:
    from ..manifest import load_validated
    from ..viz import run_mermaid, team_mermaid

    if from_run:
        from ..orchestrate import OrchestrationRecording

        rec = OrchestrationRecording.load(target)
        print(run_mermaid(rec.team, rec.run))
    else:
        print(team_mermaid(load_validated("maf_orchestration", Path(target))))
    return 0


def _cmd_orchestrate_otel(recording_path: str, out: str | None) -> int:
    from ..otel import recording_to_otlp

    otlp = recording_to_otlp(recording_path)
    rendered = json.dumps(otlp, indent=2)
    if out:
        Path(out).write_text(rendered + "\n", encoding="utf-8")
        n = len(otlp["resourceSpans"][0]["scopeSpans"][0]["spans"])
        print(f"wrote {n} GenAI spans (OTLP): {out}")
    else:
        print(rendered)
    return 0


def _cmd_orchestrate_freeze(
    recording_path: str, out_dir: str, slug: str, category: str, violation_type: str | None
) -> int:
    from ..orchestrate import OrchestrationRecording, freeze_to_corpus

    rec = OrchestrationRecording.load(recording_path)
    try:
        out = freeze_to_corpus(
            rec, out_dir, slug=slug, category=category, violation_type=violation_type
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"frozen corpus subject: {out}")
    return 0
