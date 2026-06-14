"""CLI entrypoint: python -m recette validate | run | discovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from .discovery_harness import (
    SURFACE_CORPUS,
    SURFACE_ORDER,
    discover_repo_dirs,
    run_discovery_recette,
)
from .harness import DEFAULT_CORPUS, discover_agent_dirs, run_recette

# Single source of truth for the CLI --provider choices: the llm factory's own
# provider tuple. Importing it (instead of a second hand-kept copy) keeps the CLI
# in lockstep with recette.llm.build_llm -- a vendor added there is accepted by
# the CLI with no edit, no silent gap (R5). llm pulls only stdlib + the in-repo
# http client, so this import is cheap.
from .llm import _PROVIDERS as _LLM_PROVIDERS
from .manifest import load_ground_truth, load_manifest, load_scenario
from .redteam_recette import run_scenario
from .redteam_scorecard import render as render_redteam
from .redteam_scorecard import scorecard as redteam_scorecard

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DISCOVERY_GT_SCHEMA = _REPO_ROOT / "corpus" / "schemas" / "discovery-ground-truth.schema.json"


def _cmd_validate(corpus_root: Path) -> int:
    """Validate every corpus artifact against its schema. Returns process exit code."""
    agent_dirs = discover_agent_dirs(corpus_root)
    if not agent_dirs:
        print(f"no agents found under {corpus_root}", file=sys.stderr)
        return 1
    errors = 0
    for d in agent_dirs:
        for kind, loader in (
            ("manifest", load_manifest),
            ("scenario", load_scenario),
            ("ground-truth", load_ground_truth),
        ):
            fname = "ground-truth.json" if kind == "ground-truth" else f"{kind}.json"
            try:
                loader(d / fname)
            except (ValueError, FileNotFoundError) as exc:
                errors += 1
                print(f"INVALID {d.name}/{fname}: {exc}", file=sys.stderr)
        # cross-file agent_id consistency
        try:
            ids = {
                load_manifest(d / "manifest.json")["agent_id"],
                load_scenario(d / "scenario.json")["agent_id"],
                load_ground_truth(d / "ground-truth.json")["agent_id"],
            }
            if len(ids) != 1:
                errors += 1
                print(f"INVALID {d.name}: agent_id mismatch across files {ids}", file=sys.stderr)
        except (ValueError, FileNotFoundError):
            pass  # already reported above
    # Validate the discovery repo corpus too.
    repo_errors, repo_count = _validate_repo_corpus()
    errors += repo_errors
    # Validate the standard-aligned (MAF) subject corpus.
    maf_errors, maf_count = _validate_maf_corpus()
    errors += maf_errors
    # Validate the multi-agent handoff orchestration corpus.
    orch_errors, orch_count = _validate_orchestration_corpus()
    errors += orch_errors

    if errors:
        print(f"\n{errors} validation error(s)", file=sys.stderr)
        return 1
    print(
        f"OK: {len(agent_dirs)} agents valid, {repo_count} discovery repos valid, "
        f"{maf_count} MAF subjects valid, {orch_count} orchestration teams valid"
    )
    return 0


def _validate_maf_corpus() -> tuple[int, int]:
    """Schema-validate every MAF subject (spec/actions/ground-truth). Returns (errors, count)."""
    from .maf_harness import discover_maf_dirs
    from .manifest import load_validated

    errors = 0
    count = 0
    for d in discover_maf_dirs():
        count += 1
        for kind, fname in (
            ("manifest", "spec.json"),
            ("maf_actions", "actions.json"),
            ("ground_truth", "ground-truth.json"),
        ):
            try:
                doc = load_validated(kind, d / fname)
            except (ValueError, FileNotFoundError) as exc:
                errors += 1
                print(f"INVALID maf/{d.name}/{fname}: {exc}", file=sys.stderr)
                continue
            if doc.get("agent_id") != d.name:
                errors += 1
                print(f"INVALID maf/{d.name}/{fname}: agent_id != dir name", file=sys.stderr)
    return errors, count


def _validate_orchestration_corpus() -> tuple[int, int]:
    """Schema-validate every handoff team (team/run/ground-truth). Returns (errors, count)."""
    from .maf_orchestration_harness import discover_orchestration_dirs
    from .manifest import load_validated

    errors = 0
    count = 0
    for d in discover_orchestration_dirs():
        count += 1
        for kind, fname in (
            ("maf_orchestration", "team.json"),
            ("maf_orchestration_run", "run.json"),
            ("ground_truth", "ground-truth.json"),
        ):
            try:
                doc = load_validated(kind, d / fname)
            except (ValueError, FileNotFoundError) as exc:
                errors += 1
                print(f"INVALID orchestration/{d.name}/{fname}: {exc}", file=sys.stderr)
                continue
            if doc.get("agent_id") != d.name:
                errors += 1
                print(
                    f"INVALID orchestration/{d.name}/{fname}: agent_id != dir name",
                    file=sys.stderr,
                )
    return errors, count


def _cmd_maf() -> int:
    from .maf_harness import run_maf_recette

    scorecard = run_maf_recette()
    print(scorecard.render())
    return 0 if scorecard.all_passed else 1


def _cmd_benchmark(as_json: bool) -> int:
    from .benchmark import full_benchmark, render

    bench = full_benchmark()
    print(json.dumps(bench, indent=2) if as_json else render(bench))
    return 0


def _validate_repo_corpus() -> tuple[int, int]:
    """Schema-validate discovery-ground-truth.json across every surface. Returns (errors, count)."""
    schema = json.loads(_DISCOVERY_GT_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = 0
    count = 0
    for surface in SURFACE_ORDER:
        for d in discover_repo_dirs(SURFACE_CORPUS[surface]):
            count += 1
            gt = json.loads((d / "discovery-ground-truth.json").read_text(encoding="utf-8"))
            for err in sorted(validator.iter_errors(gt), key=str):
                errors += 1
                print(
                    f"INVALID {surface}/{d.name}/discovery-ground-truth.json: {err.message}",
                    file=sys.stderr,
                )
            if gt.get("agent_repo") != d.name:
                errors += 1
                print(f"INVALID {surface}/{d.name}: agent_repo != dir name", file=sys.stderr)
    return errors, count


def _cmd_run(corpus_root: Path) -> int:
    scorecard = run_recette(corpus_root)
    print(scorecard.render())
    return 0 if scorecard.all_passed else 1


def _cmd_rag(eval_path: str, k: int) -> int:
    """RAG retrieval-quality recette: judge a retrieval tool against ground truth."""
    from .rag import DeterministicRagBackend, Document
    from .rag_eval import RagQueryTruth, ReferenceRagAdapter, judge_rag

    spec = json.loads(Path(eval_path).read_text(encoding="utf-8"))
    corpus = [Document(doc_id=d["doc_id"], text=d["text"]) for d in spec["corpus"]]
    truths = [
        RagQueryTruth(
            query=q["query"],
            relevant_ids=tuple(q["relevant_ids"]),
            top_id=q.get("top_id"),
        )
        for q in spec["queries"]
    ]
    adapter = ReferenceRagAdapter(DeterministicRagBackend(corpus))
    scorecard = judge_rag(adapter, truths, k=k)
    print(scorecard.render())
    return 0 if scorecard.all_passed else 1


def _cmd_rag_kb(action: str, doc_path: str | None, doc_id: str | None, scenario: str | None) -> int:
    """Operator knowledge-base CRUD: list/add/del/reset/apply/scenarios."""
    from .rag_store import KnowledgeBaseError, KnowledgeBaseStore

    store = KnowledgeBaseStore()
    try:
        if action == "list":
            for d in store.documents():
                flag = f"  [poison:{d.get('threat')}]" if d["poisoned"] else ""
                print(f"  {d['id']:28} {d['title']}{flag}")
            return 0
        if action == "scenarios":
            for name in store.list_scenarios():
                print(f"  {name}")
            return 0
        if action == "reset":
            print(f"reset -> baseline ({store.reset()} documents)")
            return 0
        if action == "apply":
            if not scenario:
                print("apply requires --scenario", file=sys.stderr)
                return 2
            injected = store.apply_scenario(scenario)
            print(f"applied {scenario}: injected {[d['id'] for d in injected]}")
            return 0
        if action == "add":
            if not doc_path:
                print("add requires --doc <file.json>", file=sys.stderr)
                return 2
            doc = json.loads(Path(doc_path).read_text(encoding="utf-8"))
            print(f"added {store.add(doc)['id']}")
            return 0
        if action == "del":
            if not doc_id:
                print("del requires --id", file=sys.stderr)
                return 2
            store.delete(doc_id)
            print(f"deleted {doc_id}")
            return 0
    except KnowledgeBaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"unknown rag-kb action: {action}", file=sys.stderr)
    return 2


def _cmd_publish(slug: str, owner: str, visibility: str, apply: bool) -> int:
    from .publish import publish_repo

    plan = publish_repo(slug, owner, visibility=visibility, dry_run=not apply)
    print(plan.render())
    if not apply:
        print("\n(dry-run -- nothing created. Re-run with --apply to create the repo.)")
    return 0


def _build_source_adapter(adapter_name: str):
    """Return a fresh SourceScanAdapter for one surface run (None = reference oracle)."""
    if adapter_name == "reference":
        return None  # harness default = ReferenceSourceScanAdapter
    if adapter_name == "http":
        from .http_adapter import HttpSourceScanAdapter

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


def _cmd_bundle_verify(path: str, pubkey: str | None) -> int:
    from .bundle import verify_bundle_file

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


def _cmd_agent_run(
    manifest_path: str,
    provider: str,
    model: str,
    max_steps: int,
    real: bool,
    enable_writes: bool,
    base_url: str | None,
) -> int:
    from .lane_b import run_agent
    from .llm import build_llm

    # Validate the provider/base_url combo before any file read or network call:
    # build_llm raises ValueError when openai_compat is missing its base_url.
    try:
        llm = build_llm(provider, model, base_url=base_url)  # live; key from env (R8)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    spec = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    forge = None  # default = LabForge (no side effects)
    if real:
        from .realmode import build_real_forge

        forge = build_real_forge(spec["target_system"], enable_writes=enable_writes)
        print(f"REAL MODE on {spec['target_system']} (allowlisted, writes={enable_writes})")
    result = run_agent(
        agent_id=spec["agent_id"],
        principal=spec["principal"],
        target_system=spec["target_system"],
        goal=spec["goal"],
        capability_scope=spec["capability_scope"],
        llm=llm,
        forge=forge,
        provider=provider,
        model=model,
        max_steps=max_steps,
    )
    out = Path(f"{spec['agent_id']}.recording.json")
    result.recording.save(out)
    print(f"ran {len(result.actions)} actions; recording saved to {out}")
    return 0


def _cmd_agent_replay(recording_path: str) -> int:
    from .lane_b import run_agent
    from .recording import Recording, replay_backend

    recording = Recording.load(recording_path)
    result = run_agent(
        agent_id=recording.agent_id,
        principal=recording.principal,
        target_system=recording.target_system,
        goal=recording.goal,
        capability_scope=[a["action_type"] for a in recording.actions()],
        llm=replay_backend(recording),
    )
    replayed = [a.to_dict() for a in result.actions]
    deterministic = replayed == recording.actions()
    for a in result.actions:
        print(f"  {a.action_type} {a.resource} (mode={a.mode})")
    print(f"replay deterministic: {deterministic}")
    return 0 if deterministic else 1


def _cmd_agent_freeze(recording_path: str, out_dir: str) -> int:
    from .promote import freeze_recording
    from .recording import Recording

    agent_dir = freeze_recording(Recording.load(recording_path), out_dir)
    print(f"promoted to Lane A golden: {agent_dir}")
    return 0


def _cmd_orchestrate_run(
    team_path: str,
    provider: str,
    model: str,
    base_url: str | None,
    max_steps: int,
    out: str | None,
    cache: str | None,
) -> int:
    from .llm import LlmBackend, build_llm
    from .maf_orchestration import judge_orchestration
    from .manifest import load_validated
    from .orchestrate import record

    try:
        llm: LlmBackend = build_llm(provider, model, base_url=base_url)  # live; key from env (R8)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if cache is not None:
        from .llm_cache import CachingLlm, LlmCache

        llm = CachingLlm(llm, cache=LlmCache(cache), namespace=f"{provider}:{model}")
    team = load_validated("maf_orchestration", Path(team_path))
    rec = record(team, llm, provider=provider, model=model, max_steps=max_steps)
    out_path = Path(out or f"{team['agent_id']}.orchestration.json")
    rec.save(out_path)
    verdict = judge_orchestration(team, rec.run).verdict
    print(f"recorded {len(rec.decisions)} decisions; verdict={verdict}; saved {out_path}")
    return 0


def _cmd_orchestrate_replay(recording_path: str) -> int:
    from .orchestrate import OrchestrationRecording, replay

    rec = OrchestrationRecording.load(recording_path)
    try:
        _, result = replay(rec)
    except ValueError as exc:
        print(f"replay diverged: {exc}", file=sys.stderr)
        return 1
    print(f"replay deterministic: True; verdict={result.verdict}")
    return 0


def _cmd_orchestrate_viz(target: str, from_run: bool) -> int:
    from .manifest import load_validated
    from .viz import run_mermaid, team_mermaid

    if from_run:
        from .orchestrate import OrchestrationRecording

        rec = OrchestrationRecording.load(target)
        print(run_mermaid(rec.team, rec.run))
    else:
        print(team_mermaid(load_validated("maf_orchestration", Path(target))))
    return 0


def _cmd_orchestrate_otel(recording_path: str, out: str | None) -> int:
    from .otel import recording_to_otlp

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
    from .orchestrate import OrchestrationRecording, freeze_to_corpus

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


def _cmd_report(as_json: bool) -> int:
    from .report import build_report

    report = build_report()
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.render())
    return 0 if report.all_passed else 1


def _cmd_import_maf(spec_path: str, out: str | None) -> int:
    from .import_maf import load_maf, maf_to_manifest
    from .manifest import validate

    try:
        maf = load_maf(Path(spec_path))
        spec, gaps = maf_to_manifest(maf)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"import-maf failed: {exc}", file=sys.stderr)
        return 2
    for gap in gaps:
        print(f"WARN unmapped MAF tool (no fabrication): {gap}", file=sys.stderr)
    errors = validate("manifest", spec)
    if errors:
        for err in errors:
            print(f"INVALID manifest: {err}", file=sys.stderr)
        return 2
    rendered = json.dumps(spec, indent=2)
    if out:
        Path(out).write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote agent-spec draft: {out} ({len(spec['capability_scope'])} capabilities)")
    else:
        print(rendered)
    return 0


def _cmd_redteam() -> int:
    """Replay every committed red-team scenario, print the scorecard.

    Globs corpus/sim/*.scenario.json in sorted order (deterministic, I4), runs
    each through run_scenario, aggregates with redteam_scorecard, and returns a
    non-zero exit code when any anomaly was missed (predicted verdict diverged
    from the expected verdict)."""
    sim_dir = _REPO_ROOT / "corpus" / "sim"
    outcomes = []
    for path in sorted(sim_dir.glob("*.scenario.json")):
        with path.open(encoding="utf-8") as fh:
            scenario = json.load(fh)
        outcomes.append(run_scenario(scenario))
    card = redteam_scorecard(outcomes)
    print(render_redteam(card))
    return 1 if card["missed"] else 0


def _cmd_redteam_record(args: argparse.Namespace) -> int:
    """Run a LIVE red-team attack against a target subject, freeze it to a scenario.

    A real LLM provider (key from .env, R18) drives both the attacker
    (RedTeamSimulator) and the target subject; the run is recorded and frozen via
    the Phase-2 recorder into corpus/sim/<id>.scenario.json -- a deterministic,
    replayable artifact. This live path is NOT a gate (it needs a real key)."""
    from .api._dotenv import load_dotenv
    from .llm import LlmBackend, build_llm
    from .manifest import load_validated
    from .redteam import RedTeamSimulator
    from .redteam_record import PyritAttacker, record_scenario, write_scenario
    from .simulate import UserTurns

    load_dotenv()  # R18: keys resolve from .env

    try:
        spec = load_validated("manifest", Path(args.spec))
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"invalid target spec: {exc}", file=sys.stderr)
        return 2

    try:
        subject: LlmBackend = build_llm(args.subject_provider, args.subject_model)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.cache is not None:
        from .llm_cache import CachingLlm, LlmCache

        cache = LlmCache(args.cache)
        subject = CachingLlm(
            subject, cache=cache, namespace=f"{args.subject_provider}:{args.subject_model}"
        )

    attacker: UserTurns
    if args.attacker == "pyrit":
        # Optional PyRIT driver ([real] extra); pyrit is imported lazily inside the
        # attacker's __call__, never here, so the CLI loads without the dependency.
        attacker = PyritAttacker(
            objective=args.objective or args.name,
            provider=args.attacker_provider,
            model=args.attacker_model,
            max_turns=args.max_turns,
        )
    else:
        # The native RedTeamSimulator needs a real attacker backend; the seeded
        # PyritAttacker does not, so --attacker-model is only required here.
        if not args.attacker_model:
            print("--attacker-model is required for --attacker native", file=sys.stderr)
            return 2
        try:
            attacker_backend: LlmBackend = build_llm(args.attacker_provider, args.attacker_model)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.cache is not None:
            from .llm_cache import CachingLlm, LlmCache

            cache = LlmCache(args.cache)
            attacker_backend = CachingLlm(
                attacker_backend,
                cache=cache,
                namespace=f"{args.attacker_provider}:{args.attacker_model}",
            )
        attacker = RedTeamSimulator(attacker_backend, max_turns=args.max_turns)

    tags = {
        k: v for k, v in (("owasp", args.owasp), ("mitre", args.mitre), ("nist", args.nist)) if v
    }

    scenario = record_scenario(
        spec=spec,
        subject=subject,
        user_turns=attacker,
        scenario_id=args.scenario_id,
        name=args.name,
        strategy=args.strategy,
        tags=tags,
        max_user_turns=args.max_turns,
    )

    out = write_scenario(scenario, args.out, overwrite=args.overwrite)
    print(f"froze red-team scenario: {out}")
    print(f"expected: {scenario['expected']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="recette", description="inspect_ia_agents harness")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="path to corpus/agents (default: repo corpus)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "validate", help="schema-validate all corpus artifacts (agents + discovery repos)"
    )
    sub.add_parser("run", help="run the identification recette and print the scorecard")
    disc = sub.add_parser("discovery", help="run the discovery recette over the repo corpus")
    disc.add_argument(
        "--adapter",
        choices=["reference", "http"],
        default="reference",
        help="reference = offline oracle (default); http = live Discovery :8081",
    )
    disc.add_argument(
        "--surface",
        choices=["all", *SURFACE_ORDER],
        default="all",
        help="scanner surface to score (default: all surfaces that have a corpus)",
    )
    rep = sub.add_parser("report", help="aggregate report: identification + all discovery surfaces")
    rep.add_argument("--json", action="store_true", help="emit JSON instead of text")
    bnd = sub.add_parser("bundle-verify", help="verify an Ed25519-signed policy bundle")
    bnd.add_argument("path", help="path to the policy bundle JSON")
    bnd.add_argument("--pubkey", default=None, help="pin the expected Ed25519 public key (hex)")
    agent = sub.add_parser("agent", help="Lane B live LLM agents (run / replay / freeze)")
    agent_sub = agent.add_subparsers(dest="agent_cmd", required=True)
    a_run = agent_sub.add_parser("run", help="run a live LLM agent (provider key from env)")
    a_run.add_argument(
        "manifest",
        help="Lane B manifest JSON (agent_id, principal, target_system, goal, capability_scope)",
    )
    a_run.add_argument("--provider", required=True, choices=list(_LLM_PROVIDERS))
    a_run.add_argument("--model", required=True)
    a_run.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible base URL (required for --provider openai_compat)",
    )
    a_run.add_argument("--max-steps", type=int, default=10)
    a_run.add_argument(
        "--real",
        action="store_true",
        help="act on real systems (RealForge, token + INSPECT_IA_AGENTS_REAL_ALLOWLIST via env)",
    )
    a_run.add_argument(
        "--enable-writes", action="store_true", help="allow write actions in real mode"
    )
    a_rep = agent_sub.add_parser("replay", help="deterministically replay a recording")
    a_rep.add_argument("recording", help="path to a recording JSON")
    a_frz = agent_sub.add_parser("freeze", help="promote a recording into a Lane A golden")
    a_frz.add_argument("recording", help="path to a recording JSON")
    a_frz.add_argument("--out", default="corpus/agents/correct", help="output corpus dir")
    orch = sub.add_parser(
        "orchestrate", help="end-to-end multi-agent orchestration (run / replay / freeze)"
    )
    orch_sub = orch.add_subparsers(dest="orch_cmd", required=True)
    o_run = orch_sub.add_parser("run", help="drive a team with a live LLM and record the run")
    o_run.add_argument("team", help="path to a team.json (maf_orchestration)")
    o_run.add_argument("--provider", default="groq", choices=list(_LLM_PROVIDERS))
    o_run.add_argument("--model", required=True)
    o_run.add_argument("--base-url", default=None, help="base URL for openai_compat")
    o_run.add_argument("--max-steps", type=int, default=32)
    o_run.add_argument("--out", default=None, help="recording output path")
    o_run.add_argument(
        "--cache", default=None, help="content-addressed LLM cache file (cheap, reproducible)"
    )
    o_rep = orch_sub.add_parser(
        "replay", help="deterministically replay an orchestration recording"
    )
    o_rep.add_argument("recording", help="path to an orchestration recording JSON")
    o_otel = orch_sub.add_parser(
        "otel", help="export a recording as OpenTelemetry GenAI spans (OTLP)"
    )
    o_otel.add_argument("recording", help="path to an orchestration recording JSON")
    o_otel.add_argument("--out", default=None, help="write the OTLP JSON here (default: stdout)")
    o_viz = orch_sub.add_parser(
        "viz", help="print a Mermaid diagram of a team (or a run with --run)"
    )
    o_viz.add_argument("target", help="path to a team.json, or a recording with --run")
    o_viz.add_argument(
        "--run", action="store_true", help="target is a recording; draw the actual routed path"
    )
    o_frz = orch_sub.add_parser("freeze", help="freeze a recording into a corpus subject")
    o_frz.add_argument("recording", help="path to an orchestration recording JSON")
    o_frz.add_argument(
        "--out", default="corpus/maf_orchestration/correct", help="output corpus dir"
    )
    o_frz.add_argument("--slug", required=True, help="subject slug (dir + agent_id)")
    o_frz.add_argument("--category", choices=["correct", "incorrect"], default="correct")
    o_frz.add_argument("--violation-type", default=None, help="required when category=incorrect")
    sub.add_parser(
        "maf", help="run the standard-aligned (MAF) identification recette and print the scorecard"
    )
    bench = sub.add_parser(
        "benchmark", help="judge accuracy benchmark per dimension / style / area"
    )
    bench.add_argument("--json", action="store_true", help="emit JSON instead of text")
    imp = sub.add_parser(
        "import-maf",
        help="import a Microsoft Agent Framework declarative spec into a unified manifest draft",
    )
    imp.add_argument("spec", help="path to a MAF spec (.yaml/.yml needs [maf], or .json)")
    imp.add_argument("--out", default=None, help="write the draft here (default: stdout)")
    rag = sub.add_parser("rag", help="run the RAG retrieval-quality recette (scorecard)")
    rag.add_argument(
        "--eval",
        default="corpus/rag/retrieval-eval.json",
        help="ground-truth eval file (corpus + queries)",
    )
    rag.add_argument("--k", type=int, default=5, help="number of docs to retrieve per query")
    ragkb = sub.add_parser("rag-kb", help="operator knowledge-base CRUD (list/add/del/reset/apply)")
    ragkb.add_argument("action", choices=["list", "add", "del", "reset", "apply", "scenarios"])
    ragkb.add_argument("--doc", default=None, help="document JSON file (for add)")
    ragkb.add_argument("--id", default=None, dest="doc_id", help="document id (for del)")
    ragkb.add_argument("--scenario", default=None, help="scenario name (for apply)")
    sub.add_parser(
        "redteam",
        help="run the deterministic red-team recette and print the scorecard",
    )
    rtr = sub.add_parser(
        "redteam-record",
        help="run a LIVE red-team attack and freeze it into a replayable scenario",
    )
    rtr.add_argument("--spec", required=True, help="target manifest JSON (subject under attack)")
    # attacker-provider/model are used only by the NATIVE attacker; the seeded
    # PyritAttacker ignores them, so neither is argparse-required (the native
    # branch validates --attacker-model in code below).
    rtr.add_argument("--attacker-provider", default="groq", choices=list(_LLM_PROVIDERS))
    rtr.add_argument("--attacker-model", default=None)
    rtr.add_argument("--subject-provider", default="groq", choices=list(_LLM_PROVIDERS))
    rtr.add_argument("--subject-model", required=True)
    rtr.add_argument(
        "--strategy",
        choices=["crescendo", "skeleton_key", "tool_injection"],
        default="crescendo",
    )
    rtr.add_argument("--max-turns", type=int, default=4, help="attacker turns (and recorder cap)")
    rtr.add_argument(
        "--attacker",
        choices=["native", "pyrit"],
        default="native",
        help="attack driver: native RedTeamSimulator (default) or optional PyRIT ([real] extra)",
    )
    rtr.add_argument(
        "--objective",
        default=None,
        help="adversarial objective for the pyrit attacker (defaults to the scenario name)",
    )
    rtr.add_argument("--scenario-id", required=True, help="frozen scenario id (file stem)")
    rtr.add_argument("--name", required=True, help="human-readable scenario name")
    rtr.add_argument("--owasp", default=None, help="OWASP ASI tag (optional)")
    rtr.add_argument("--mitre", default=None, help="MITRE ATLAS tag (optional)")
    rtr.add_argument("--nist", default=None, help="NIST tag (optional)")
    rtr.add_argument("--out", default="corpus/sim", help="output dir (default: corpus/sim)")
    rtr.add_argument(
        "--cache", default=None, help="content-addressed LLM cache file (cheap, reproducible)"
    )
    rtr.add_argument("--overwrite", action="store_true", help="replace an existing frozen scenario")
    pub = sub.add_parser("publish", help="publish a corpus repo tree to a real GitHub repo")
    pub.add_argument("slug", help="repo slug under corpus/repos/")
    pub.add_argument("--owner", required=True, help="GitHub owner/org for the new repo")
    pub.add_argument("--visibility", choices=["private", "public"], default="private")
    pub.add_argument(
        "--apply", action="store_true", help="actually create + push (default: dry-run)"
    )
    return parser


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
    if args.command == "redteam":
        return _cmd_redteam()
    if args.command == "redteam-record":
        return _cmd_redteam_record(args)
    if args.command == "publish":
        return _cmd_publish(args.slug, args.owner, args.visibility, args.apply)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
