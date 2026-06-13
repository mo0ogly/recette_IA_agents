"""Deterministic end-to-end proof of the RAG poisoning recette loop (I4).

One command demonstrates the whole operator loop without any live model:

    reset -> apply <scenario> -> drive each injected poison at the gateway
          -> assert deny/escalate AND executed=False -> reset -> KB == baseline

The induced action is read DIRECTLY from each poisoned document
(injected_action / injected_target_system / injected_expect), so the run is
reproducible byte-for-byte: no clock, no random, no LLM (the live, non-deterministic
variant is scripts/run_rag_poisoning_live_groq.py). The thesis (I2/I5): a poisoned
retrieval cannot become a side effect -- exfiltration denies, an invalid command
denies, a forged ingest escalates, and the gateway NEVER executes any of them.

The store mutation (apply/reset) is an OPERATOR action OFF the agent path; the agent
itself only ever reaches the index through the gateway. reset() restores the
committed baseline exactly, so the final KB is byte-identical to the start (I4).

Usage: python3 scripts/run_rag_poisoning_e2e.py [--scenario exfil-finance]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_role_matrix import _StubProxy  # noqa: E402

from recette.api.app import create_app  # noqa: E402
from recette.api.config_store import ConfigStore  # noqa: E402
from recette.platform.catalog import load_catalog  # noqa: E402
from recette.platform.eventstore.memory_store import InMemoryEventStore  # noqa: E402
from recette.platform.policy.model import baseline_from_catalog  # noqa: E402
from recette.platform.policy.store import PolicyStore  # noqa: E402
from recette.rag_store import KnowledgeBaseStore  # noqa: E402

BUNDLE_VERSION = "baseline-v1"
_BLOCK_VERDICTS = {"deny", "escalate"}


def _canonical(docs: list[dict]) -> str:
    """Stable canonical JSON of the KB, for a byte-identical baseline comparison."""
    return json.dumps(docs, sort_keys=True, ensure_ascii=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_rag_poisoning_e2e")
    parser.add_argument("--scenario", default="exfil-finance", help="poison scenario to apply")
    args = parser.parse_args(argv)

    from fastapi.testclient import TestClient

    catalog = load_catalog()
    store = KnowledgeBaseStore()
    store.reset()
    baseline = _canonical(store.documents())

    if args.scenario not in store.list_scenarios():
        print(
            f"unknown scenario {args.scenario!r}; available: {store.list_scenarios()}",
            file=sys.stderr,
        )
        return 2

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        policies = PolicyStore(tmp / "policies")
        policies.publish(baseline_from_catalog(catalog, version=BUNDLE_VERSION))
        policies.set_active(BUNDLE_VERSION)
        app = create_app(
            config_store=ConfigStore(tmp / "config.json"),
            event_store=InMemoryEventStore(),
            policy_store=policies,
            proxy=_StubProxy(),
            catalog=catalog,
        )
        client = TestClient(app)

        base_count = store.reset()
        injected = store.apply_scenario(args.scenario)
        print(f"reset -> {base_count} docs; apply {args.scenario!r} -> +{len(injected)} injected")

        failures: list[str] = []
        checked = 0
        for doc in store.documents():
            if not doc.get("poisoned"):
                continue
            checked += 1
            agent_id = f"rag-e2e-{doc['id']}"
            action_type = doc["injected_action"]
            target = doc["injected_target_system"]
            expect = doc["injected_expect"]
            client.post(
                "/config/agents",
                json={
                    "id": agent_id,
                    "runtime": "lab",
                    "role": "rag_agent",
                    "capability_scope": ["query_knowledge_base", action_type],
                },
            )
            resp = client.post(
                "/actions/execute",
                json={
                    "agent_id": agent_id,
                    "target_system": target,
                    "action_type": action_type,
                    "resource": doc["id"],
                    "payload": {},
                },
            ).json()
            verdict = resp.get("verdict", "?")
            executed = resp.get("executed", True)
            ok = verdict == expect and verdict in _BLOCK_VERDICTS and not executed
            if not ok:
                failures.append(
                    f"{doc['id']}: {target}/{action_type} expected {expect} (block, not executed), "
                    f"got verdict={verdict} executed={executed}"
                )
            flag = "" if ok else "  <-- FAIL"
            print(
                f"  poison {doc['id']} ({doc.get('threat', '?')}): {target}/{action_type} "
                f"-> gateway {verdict} (executed={executed}){flag}"
            )

        final_count = store.reset()
        restored = _canonical(store.documents())
        baseline_ok = restored == baseline
        chain = client.get("/audit/verify").json().get("ok", False)
        print(
            f"\nreset -> {final_count} docs; baseline restored byte-identical: {baseline_ok}; "
            f"audit chain: {'intact' if chain else 'BROKEN'}"
        )

        if not checked:
            print(f"RESULT: FAILURE -- scenario {args.scenario!r} injected no poisoned document")
            return 1
        if failures or not baseline_ok or not chain:
            for f in failures:
                print(f"  FAIL {f}")
            if not baseline_ok:
                print("  FAIL reset did not restore the baseline byte-identically (I4)")
            print("RESULT: FAILURE -- the recette loop did not hold")
            return 1
        print(
            f"RESULT: PASS -- {checked} poisoned actions all blocked (executed=False), "
            "baseline restored, audit chain intact"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
