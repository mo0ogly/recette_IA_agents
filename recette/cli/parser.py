"""argparse parser for the recette CLI (subcommand definitions)."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..discovery_harness import SURFACE_ORDER
from ..harness import DEFAULT_CORPUS
from ..llm import _PROVIDERS as _LLM_PROVIDERS


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
    rcv = sub.add_parser(
        "receipts-verify", help="verify a signed context-receipt export off-platform"
    )
    rcv.add_argument("path", help="path to the receipt export JSON envelope")
    rcv.add_argument("--pubkey", default=None, help="pin the expected Ed25519 public key (hex)")
    rcv.add_argument("--json", action="store_true", help="emit the JSON verdict instead of text")
    rca = sub.add_parser(
        "receipts-attest",
        help="verify a selective-disclosure attestation (signed root + one inclusion proof)",
    )
    rca.add_argument(
        "--attestation", required=True, help="path to the signed root-attestation JSON"
    )
    rca.add_argument("--proof", required=True, help="path to the inclusion-proof JSON")
    rca.add_argument("--pubkey", default=None, help="pin the expected Ed25519 public key (hex)")
    rca.add_argument("--json", action="store_true", help="emit the JSON verdict instead of text")
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
    surface_parser = sub.add_parser(
        "surface",
        help="per-surface detection recette (does the discovery probe SEE each agent?)",
    )
    surface_parser.add_argument(
        "--recording",
        default=None,
        help="score a discoveryprobe broker capture recording (JSON file) "
        "instead of the in-bench corpus projection",
    )
    analyze = sub.add_parser(
        "analyze",
        help="behavioral-analysis engine: run/replay tunable waves over agent evidence",
    )
    analyze_sub = analyze.add_subparsers(dest="analyze_cmd", required=True)
    an_run = analyze_sub.add_parser(
        "wave", help="run one analysis wave (evidence + profile) -> report"
    )
    an_run.add_argument(
        "--evidence", required=True, help="evidence bundle folder or a bundle.json file"
    )
    an_run.add_argument(
        "--profile", default=None, help="AnalysisProfile JSON (omit for the default profile)"
    )
    an_run.add_argument(
        "--threat",
        default=None,
        help="override the threat hypothesis (neutral|exfil|escalation|tunneling|supply_chain)",
    )
    an_run.add_argument(
        "--json", action="store_true", help="emit the full report as JSON (default: summary)"
    )
    an_rep = analyze_sub.add_parser(
        "replay", help="re-run a wave and assert the report is byte-identical (reproducibility)"
    )
    an_rep.add_argument("--evidence", required=True, help="evidence bundle folder or bundle.json")
    an_rep.add_argument("--profile", default=None, help="AnalysisProfile JSON (default profile)")
    an_rep.add_argument("--threat", default=None, help="override the threat hypothesis")
    an_rep.add_argument(
        "--report", required=True, help="prior report JSON to check byte-equality against"
    )
    an_met = analyze_sub.add_parser(
        "metrics", help="ground-truth metrics for a wave (confusion, ROC, separation AUC)"
    )
    an_met.add_argument("--evidence", required=True, help="evidence bundle (needs ground_truth)")
    an_met.add_argument("--profile", default=None, help="AnalysisProfile JSON")
    an_met.add_argument("--threat", default=None, help="override the threat hypothesis")
    an_met.add_argument("--json", action="store_true", help="emit the full metrics block as JSON")
    an_sweep = analyze_sub.add_parser(
        "sweep", help="sweep a threshold knob across values -> confusion per setting"
    )
    an_sweep.add_argument("--evidence", required=True, help="evidence bundle (needs ground_truth)")
    an_sweep.add_argument("--profile", default=None, help="AnalysisProfile JSON")
    an_sweep.add_argument("--threat", default=None, help="override the threat hypothesis")
    an_sweep.add_argument(
        "--knob", required=True, help="threshold key to sweep (e.g. ghost_host_tolerance)"
    )
    an_sweep.add_argument("--values", required=True, help="comma-separated values (e.g. 0,1,2,3)")
    an_abl = analyze_sub.add_parser(
        "ablate", help="per-lens ablation: drop each lens, measure the detection delta"
    )
    an_abl.add_argument("--evidence", required=True, help="evidence bundle (needs ground_truth)")
    an_abl.add_argument("--profile", default=None, help="AnalysisProfile JSON")
    an_abl.add_argument("--threat", default=None, help="override the threat hypothesis")
    an_exp = analyze_sub.add_parser(
        "export", help="write a self-contained, reproducible experiment package"
    )
    an_exp.add_argument("--evidence", required=True, help="evidence bundle folder or bundle.json")
    an_exp.add_argument("--profile", default=None, help="AnalysisProfile JSON")
    an_exp.add_argument("--threat", default=None, help="override the threat hypothesis")
    an_exp.add_argument("--out", required=True, help="output folder for the experiment package")
    an_cor = analyze_sub.add_parser(
        "correlate",
        help="correlate behavioral wave with static discovery scan -> quadrant report",
    )
    an_cor.add_argument(
        "--profile", default=None, help="AnalysisProfile JSON (omit for the default profile)"
    )
    an_cor.add_argument(
        "--threat",
        default=None,
        help="override the threat hypothesis (neutral|exfil|escalation|tunneling|supply_chain)",
    )
    an_cor.add_argument(
        "--json", action="store_true", help="emit the full report as JSON (default: summary)"
    )
    sub.add_parser(
        "redteam",
        help="run the deterministic red-team recette and print the scorecard",
    )
    rtp = sub.add_parser(
        "redteam-promote",
        help="freeze a caught red-team anomaly into a negative corpus subject",
    )
    rtp.add_argument("--scenario-id", required=True, help="scenario id to promote (MAF or git)")
    rtp.add_argument(
        "--out",
        default=None,
        help="output corpus root (default: family-derived -- "
        "corpus/agents for git, corpus/maf_agents for MAF)",
    )
    rtp.add_argument(
        "--overwrite", action="store_true", help="replace an existing promoted subject (I1)"
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
