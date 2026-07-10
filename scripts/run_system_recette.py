"""System recette: exercise the whole app live, beyond unit tests.

Unit tests prove a function in isolation; they miss the "green but a simple access
crashes / there are duplicates / the wiring is an incoherent patchwork" failures.
This harness boots the REAL app (real catalog, policy, stores, gateway) and checks
the system as a whole:

  LEG A -- COHERENCE (the patchwork detector)
    A1 every path the frontend client calls maps to a real backend route
    A2 no duplicate (method, path) route registered twice
    A3 catalog has no duplicate (target_system, action_type)
    A4 RAG knowledge base has unique document ids; scenario names are valid slugs

  LEG B -- LIVE SMOKE (a simple access must not 500)
    every parameter-free GET endpoint answers < 500

  LEG C -- FLOW (RAG x campaigns x agents through the gateway)
    C1 RAG lifecycle: reset -> list -> apply scenario (poison present) -> reset (gone)
    C2 a RAG poisoning campaign runs through the live gateway with the right verdicts
    C3 an agent ingest_document is escalated, never executed (I2 anti-backdoor)

Exit 0 if every leg passes, 1 otherwise. Add --live to also drive a real Groq LLM
against the poisoned knowledge base (governance proof on a live model).

Usage: python3 scripts/run_system_recette.py [--live]
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recette.api.app import create_app  # noqa: E402
from recette.api.config_store import ConfigStore  # noqa: E402
from recette.campaign import CampaignRunner, load_campaign  # noqa: E402
from recette.platform.catalog import load_catalog  # noqa: E402
from recette.platform.eventstore.memory_store import InMemoryEventStore  # noqa: E402
from recette.platform.policy.model import baseline_from_catalog  # noqa: E402
from recette.platform.policy.store import PolicyStore  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CLIENT_TS = REPO / "console" / "src" / "api" / "client.ts"


class _Report:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {name}{'' if ok else '  -> ' + detail}")
        if not ok:
            self.failures.append(f"{name}: {detail}")


def _iter_routes(app):  # type: ignore[no-untyped-def]
    """Yield every real (path, methods) route, descending into included routers.

    FastAPI >= 0.116 no longer flattens ``include_router`` into ``app.routes``:
    each include becomes an ``_IncludedRouter`` wrapper whose actual routes live
    under ``original_router.routes``. Walk both shapes so the coherence check
    sees the same routes regardless of the FastAPI version (a bare ``app.routes``
    scan finds only 5 default routes on newer FastAPI, marking every frontend
    path an orphan). Any object exposing ``path`` + ``methods`` is a leaf route.
    """
    stack = list(app.routes)
    while stack:
        r = stack.pop()
        if hasattr(r, "path") and hasattr(r, "methods"):
            yield r
        inner = getattr(r, "original_router", None)
        if inner is not None and hasattr(inner, "routes"):
            stack.extend(inner.routes)


def _route_templates(app) -> set[str]:  # type: ignore[no-untyped-def]
    return {r.path for r in _iter_routes(app)}


def _route_pairs(app) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    pairs = []
    for r in _iter_routes(app):
        for m in r.methods:
            if m != "HEAD":
                pairs.append((m, r.path))
    return pairs


def _matcher(templates: set[str]):  # type: ignore[no-untyped-def]
    compiled = [re.compile("^" + re.sub(r"\{[^}]+\}", r"[^/]+", t) + "$") for t in templates]

    def matches(path: str) -> bool:
        base = path.split("?")[0]
        return any(rx.match(base) for rx in compiled)

    return matches


def _frontend_paths() -> set[str]:
    src = CLIENT_TS.read_text(encoding="utf-8")
    paths: set[str] = set()
    # template-literal calls first: `/a/${x}/b` -> /a/placeholder/b
    for m in re.finditer(r"request<[^>]*>\(\s*`([^`]+)`", src):
        paths.add(re.sub(r"\$\{[^}]+\}", "placeholder", m.group(1)).split("?")[0])
    # plain string calls: "/a/b"
    for m in re.finditer(r'request<[^>]*>\(\s*"([^"$?]+)', src):
        paths.add(m.group(1).split("?")[0])
    return {p.rstrip("/") or "/" for p in paths}


def leg_a_coherence(app, report: _Report) -> None:  # type: ignore[no-untyped-def]
    print("LEG A -- coherence")
    templates = _route_templates(app)
    matches = _matcher(templates)
    # A1: every frontend path maps to a backend route (drop pure prefixes of a
    # longer template, e.g. /rag/scenario is only the prefix of /rag/scenario/X/apply).
    fe = _frontend_paths()
    real = {p for p in fe if not any(t != p and t.startswith(p + "/") for t in fe)}
    unmatched = sorted(p for p in real if not matches(p))
    report.check("A1 frontend paths map to backend routes", not unmatched, f"orphans: {unmatched}")
    # A2: no duplicate (method, path)
    pairs = _route_pairs(app)
    dups = sorted({p for p in pairs if pairs.count(p) > 1})
    report.check("A2 no duplicate route", not dups, f"dups: {dups}")
    # A3: catalog uniqueness
    specs = list(load_catalog().all())
    keys = [(s.target_system, s.action_type) for s in specs]
    report.check("A3 catalog has no duplicate action", len(keys) == len(set(keys)))
    # A4: RAG ids unique + scenario names valid
    from recette.rag_store import KnowledgeBaseStore

    kb = KnowledgeBaseStore()
    kb.reset()
    ids = [d["id"] for d in kb.documents()]
    report.check("A4a RAG document ids unique", len(ids) == len(set(ids)))
    slug = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
    bad = [s for s in kb.list_scenarios() if not slug.fullmatch(s)]
    report.check("A4b scenario names are valid slugs", not bad, f"bad: {bad}")


def leg_b_smoke(client, app, report: _Report) -> None:  # type: ignore[no-untyped-def]
    print("LEG B -- live smoke (no parameterless GET may 500)")
    # /events/stream and /proxy/wire/stream are infinite streaming responses;
    # TestClient.get would block forever reading them. Each is exercised by its
    # own dedicated test (tests/test_api_wire_stream.py for the wire stream).
    skip = {
        "/openapi.json",
        "/docs",
        "/redoc",
        "/docs/oauth2-redirect",
        "/events/stream",
        "/proxy/wire/stream",
    }
    for m, path in sorted(_route_pairs(app)):
        if m != "GET" or "{" in path or path in skip:
            continue
        status = client.get(path).status_code
        report.check(f"B GET {path}", status < 500, f"status {status}")


def leg_c_flow(client, report: _Report) -> None:  # type: ignore[no-untyped-def]
    print("LEG C -- flow (RAG x campaigns x agents)")
    # C1 RAG lifecycle
    client.post("/rag/reset")
    base = {d["id"] for d in client.get("/rag/documents").json()["documents"]}
    client.post("/rag/scenario/exfil-finance/apply")
    after = {d["id"] for d in client.get("/rag/documents").json()["documents"]}
    report.check("C1a apply scenario injects poison", "scn-exfil-finance" in after)
    client.post("/rag/reset")
    back = {d["id"] for d in client.get("/rag/documents").json()["documents"]}
    report.check("C1b reset restores baseline", back == base and "scn-exfil-finance" not in back)
    # C2 a RAG poisoning campaign through the live gateway
    runner = CampaignRunner(client)
    doc = load_campaign(REPO / "campaigns" / "rag" / "rag-poisoned-exfil.campaign.json")
    rep = runner.run(doc)
    report.check("C2 rag-poisoned-exfil campaign verdicts", rep.ok, f"counts={rep.counts}")
    # C3 anti-backdoor
    client.post(
        "/config/agents",
        json={
            "id": "sys-rag",
            "runtime": "lab",
            "role": "rag_agent",
            "capability_scope": ["knowledge_base"],
        },
    )
    resp = client.post(
        "/actions/execute",
        json={
            "agent_id": "sys-rag",
            "target_system": "knowledge_base",
            "action_type": "ingest_document",
            "resource": "kb/x",
            "payload": {},
        },
    ).json()
    report.check(
        "C3 agent ingest escalated not executed (I2)",
        resp.get("verdict") == "escalate" and not resp.get("executed"),
        f"verdict={resp.get('verdict')} executed={resp.get('executed')}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_system_recette")
    parser.add_argument("--live", action="store_true", help="also run the live Groq leg")
    args = parser.parse_args(argv)

    from fastapi.testclient import TestClient

    catalog = load_catalog()
    report = _Report()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        policies = PolicyStore(tmp / "policies")
        policies.publish(baseline_from_catalog(catalog, version="baseline-v1"))
        policies.set_active("baseline-v1")
        app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=policies,
            catalog=catalog,
        )
        client = TestClient(app)

        leg_a_coherence(app, report)
        leg_b_smoke(client, app, report)
        leg_c_flow(client, report)

    if args.live:
        print("LEG D -- live Groq poisoning")
        from run_rag_poisoning_live_groq import main as live_main

        rc = live_main([])
        report.check("D live poisoning blocked (0 leak)", rc == 0)

    print(
        f"\n{'SYSTEM RECETTE PASS' if not report.failures else 'SYSTEM RECETTE FAIL'} -- "
        f"{len(report.failures)} failure(s)"
    )
    return 0 if not report.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
