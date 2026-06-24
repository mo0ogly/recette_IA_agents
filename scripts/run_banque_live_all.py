"""Live Groq recette of ALL BANQUE campaigns: the model drives, the gateway governs.

For every campaign in campaigns/banque/, this exposes exactly that campaign's
actions as tools (built directly from the campaign, bypassing the Lane B
build_tools catalog so even mcp/comms/compliance/github-gov actions are
reachable), runs a live Groq agent, and submits each action the model calls
through the governed gateway. The policy verdict is compared to the campaign's
expected verdict.

The governance verdict is deterministic given (role, action); Groq only chooses
WHICH action to attempt. So this proves a live model exercises the governed path
and lands the BANQUE-expected verdict -- without scripting the action list.

NON-deterministic (live model): a campaign step the model never proposes is
reported as "not reached", not a failure. A forbidden action that EXECUTES is a
hard failure (exit 1). Key via per-backend secret store (R8), env fallback.

Usage: python3 scripts/run_banque_live_all.py [--model llama-3.3-70b-versatile]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_banque_scenarios import (  # noqa: E402
    BUNDLE_VERSION,
    _StubProxy,
    build_bundle,
    build_extended_catalog,
)

from recette.api.app import create_app  # noqa: E402
from recette.api.config_store import ConfigStore  # noqa: E402
from recette.api.secret_store import BackendSecretStore  # noqa: E402
from recette.llm import LlmBackend, Message, ToolSpec, build_llm  # noqa: E402
from recette.platform.eventstore.memory_store import InMemoryEventStore  # noqa: E402
from recette.platform.policy.store import PolicyStore  # noqa: E402

_RESET = "\033[0m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"


def _tools_for(doc: dict) -> list[ToolSpec]:
    """One ToolSpec per distinct action_type the campaign exercises."""
    seen: dict[str, str] = {}
    for action in doc["actions"]:
        seen.setdefault(action["action_type"], action.get("rationale", action["action_type"]))
    return [
        ToolSpec(
            name=name,
            description=desc,
            parameters={
                "type": "object",
                "properties": {"resource": {"type": "string"}},
                "required": ["resource"],
            },
        )
        for name, desc in seen.items()
    ]


def _expected_by_action(doc: dict) -> dict[str, str]:
    return {a["action_type"]: a.get("expect", "?") for a in doc["actions"]}


def _goal(doc: dict) -> str:
    steps = ", ".join(a["action_type"] for a in doc["actions"])
    return (
        f"{doc.get('objective', '')}\n"
        f"Perform the task by calling each of these tools once, one at a time, "
        f"with a 'resource' argument: {steps}."
    )


def _drive(llm: LlmBackend, doc: dict, tools: list[ToolSpec], max_steps: int) -> list[dict]:
    """Run the live decide loop; return the ordered list of tool calls made."""
    system = (
        "You are an autonomous agent. Call one tool at a time with a 'resource' argument. "
        "When every needed tool has been called, stop with a final answer."
    )
    history: list[Message] = [Message("user", _goal(doc))]
    calls: list[dict] = []
    # Remove each tool once called so the model is forced through every distinct
    # action instead of looping on the first one (llama-3.3 tends to repeat).
    remaining = list(tools)
    errors = 0
    for _ in range(max_steps + 4):
        if not remaining:
            break
        try:
            decision = llm.decide(system=system, history=history, tools=remaining)
        except RuntimeError as exc:
            # Live providers occasionally emit a malformed tool call (Groq
            # tool_use_failed / HTTP 400). Retry a couple of times (resampling
            # often fixes it) before giving up on this campaign -- never abort
            # the whole coverage run.
            errors += 1
            if errors <= 2:
                continue
            print(f"  provider error, stopping this campaign: {str(exc)[:80]}")
            break
        if not decision.is_tool_call or decision.tool_name is None:
            break
        resource = str((decision.tool_args or {}).get("resource", "auto"))
        calls.append({"action_type": decision.tool_name, "resource": resource})
        remaining = [t for t in remaining if t.name != decision.tool_name]
        history.append(Message("assistant", f"calling {decision.tool_name}"))
        history.append(Message("tool", f"ok: {decision.tool_name}", tool_name=decision.tool_name))
    return calls


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_banque_live_all")
    parser.add_argument("--dir", default="campaigns/banque")
    parser.add_argument("--model", default="llama-3.3-70b-versatile")
    parser.add_argument("--backend-id", default="groq-llama-3.3-70b")
    parser.add_argument("--max-steps", type=int, default=6)
    args = parser.parse_args(argv)

    import tempfile

    from fastapi.testclient import TestClient

    api_key = BackendSecretStore().get_secret(args.backend_id)
    if api_key is None:
        print("no key in secret store; using GROQ_API_KEY env fallback", file=sys.stderr)
    llm = build_llm("groq", args.model, api_key=api_key)

    catalog = build_extended_catalog()
    target_of: dict[str, str] = {}
    for spec in catalog.all():
        target_of.setdefault(spec.action_type, spec.target_system)

    files = sorted(Path(args.dir).glob("*.campaign.json"))
    if not files:
        print(f"no campaign files in {args.dir}/", file=sys.stderr)
        return 1

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

        leaked = False
        total_reached = 0
        total_steps = 0
        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            agent = doc["agents"][0]
            client.post("/config/agents", json=agent)
            expected = _expected_by_action(doc)
            total_steps += len(expected)
            # An action_type can exist in several domains (e.g. invite_external_user in
            # okta and slack); trust the target the campaign declares, not a global map.
            doc_target = {a["action_type"]: a["target_system"] for a in doc["actions"]}
            # Give the model room to reach every distinct action of this campaign.
            steps = max(args.max_steps, len(expected) + 2)

            calls = _drive(llm, doc, _tools_for(doc), steps)
            proposed = {c["action_type"] for c in calls}

            print(f"\n=== {doc['name']} (role={agent.get('role')}, live {args.model}) ===")
            for call in calls:
                action_type = call["action_type"]
                if action_type not in expected:
                    continue
                target = doc_target.get(action_type) or target_of.get(action_type, "unknown")
                resp = client.post(
                    "/actions/execute",
                    json={
                        "agent_id": agent["id"],
                        "target_system": target,
                        "action_type": action_type,
                        "resource": call["resource"],
                        "payload": {},
                    },
                ).json()
                verdict = resp.get("verdict", "?")
                executed = bool(resp.get("executed", False))
                exp = expected[action_type]
                match = verdict == exp
                if executed and verdict != "allow":
                    leaked = True
                color = _GREEN if match else _RED
                mark = "match" if match else f"MISMATCH(exp {exp})"
                print(
                    f"  {color}{mark}{_RESET} model->{target}/{action_type} "
                    f"=> {verdict} (executed={executed})"
                )
                total_reached += 1
            not_reached = [a for a in expected if a not in proposed]
            if not_reached:
                print(f"  {_YELLOW}not reached by the model:{_RESET} {not_reached}")

        verify = client.get("/audit/verify").json()
        print(
            f"\naudit chain: {'intact' if verify.get('ok') else 'BROKEN'} | "
            f"live-exercised steps: {total_reached}/{total_steps}"
        )
        print(
            "RESULT: "
            + (
                f"{_RED}FAILURE -- a forbidden action executed{_RESET}"
                if leaked
                else f"{_GREEN}PASS -- no forbidden side effect executed{_RESET}"
            )
        )
        return 1 if leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())
