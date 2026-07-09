"""AG2 (AutoGen) group-chat driver that plugs into recette's orchestration model.

Some teams are authored to run on AG2's ``GroupChat`` + ``GroupChatManager``
(the poc_medical shape: an attacker/target/auditor round-robin). This module
runs such a team on the *real* AG2 runtime while keeping every recette
invariant, then emits the SAME ``OrchestrationRun`` (order + tool calls) the
native ``recette.orchestrate.drive`` produces -- so the run is judged, replayed
and frozen by the existing machinery unchanged (``judge_orchestration``,
``orchestration_graph``, ``freeze_to_corpus``).

How the invariants survive AG2:
  - Mediation / offline / R8: every agent is backed by ``RecetteAG2Client``, a
    custom AG2 model client that delegates to a recette ``LlmBackend``. AG2 makes
    NO network call of its own; with a ``StubLlm``/``ReplayLlm`` backend the whole
    run is offline and deterministic. The same backend is shared by every agent,
    so the provider never differs between agents (RETEX 2026-04-08: mixing
    providers across agents froze the poc_medical pipeline).
  - Determinism (I4): the manager's speaker selection is a pure round-robin
    callable (never the LLM), so the speaker order is a fixed function of the
    participant list -- not a model choice.

AG2 is an OPTIONAL heavy dependency (extra ``ag2``), lazily imported inside
``drive_ag2`` exactly like the pyrit-backed red-team path; the module imports
fine without it, and the CLI / core recette never pull it in (R20/R22).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .llm import LlmBackend, Message, ToolSpec
from .maf_orchestration import OrchestrationRun, ToolCall
from .tracking import SessionTracker, TrackedExchange

_SYSTEM_FALLBACK = "You are a participant in a multi-agent team. Answer for your role."
_DEFAULT_MAX_ROUND = 12

# A generated tool name decodes to (tool_kind, target) without parsing the name,
# mirroring recette.orchestrate so a captured AG2 tool call maps to a recette
# ToolCall with the participant's declared identity.
_ToolMeta = dict[str, tuple[str, str]]


def _agent_tool_specs(participant: dict) -> tuple[list[dict], _ToolMeta]:
    """OpenAI-wire function specs for a participant's declared tools + a decode map."""
    specs: list[dict] = []
    meta: _ToolMeta = {}
    for i, tool in enumerate(participant.get("tools", [])):
        name = f"use_{tool['tool_kind']}_{i}"
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Invoke the {tool['tool_kind']} tool {tool['target']}.",
                    "parameters": {
                        "type": "object",
                        "properties": {"approved": {"type": "boolean"}},
                    },
                },
            }
        )
        meta[name] = (tool["tool_kind"], tool["target"])
    return specs, meta


def _messages_to_history(messages: list[dict]) -> tuple[str, list[Message]]:
    """Split an AG2/OpenAI message list into (system, recette history)."""
    system = _SYSTEM_FALLBACK
    history: list[Message] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content") or ""
        if role == "system":
            if content:
                system = content
            continue
        # Collapse every non-system turn to plain text history: the driver only
        # needs the conversation so far to ask the backend for the next line.
        norm_role = "assistant" if role == "assistant" else "user"
        history.append(Message(role=norm_role, content=content if isinstance(content, str) else ""))
    return system, history


def _tools_from_params(params: dict) -> list[ToolSpec]:
    out: list[ToolSpec] = []
    for t in params.get("tools", []) or []:
        fn = t.get("function", {})
        out.append(
            ToolSpec(
                name=fn.get("name", ""),
                description=fn.get("description", ""),
                parameters=fn.get("parameters", {}),
            )
        )
    return out


class RecetteAG2Client:
    """AG2 custom model client backed by a recette ``LlmBackend``.

    Registered on every ConversableAgent via ``register_model_client``. AG2 calls
    ``create(params)`` with an OpenAI-shaped request; we translate it to a
    ``LlmBackend.decide`` call and wrap the ``LlmDecision`` back into the minimal
    OpenAI ChatCompletion shape AG2 consumes. No network, no key: the backend is
    whatever recette injected (StubLlm offline, GroqLlm live).
    """

    # AG2 instantiates the client as ``cls(config=<config_entry>, **kwargs)``.
    # The live LlmBackend is passed through the registration kwargs (not the
    # JSON-serialisable config), so a secret/key never lands in llm_config (R8).
    def __init__(self, config: dict, backend: LlmBackend | None = None, **_: Any) -> None:
        self._model = config.get("model", "")
        if backend is None:
            raise ValueError("RecetteAG2Client requires a backend= kwarg at registration")
        self._backend = backend

    def create(self, params: dict) -> Any:
        system, history = _messages_to_history(params.get("messages", []))
        decision = self._backend.decide(
            system=system, history=history, tools=_tools_from_params(params)
        )
        return _wrap_response(decision, self._model)

    def message_retrieval(self, response: Any) -> list:
        """Return the assistant message(s) AG2 appends to the conversation."""
        return [choice.message for choice in response.choices]

    def cost(self, response: Any) -> float:
        return 0.0

    @staticmethod
    def get_usage(response: Any) -> dict:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0,
            "model": getattr(response, "model", ""),
        }


class _Msg:
    def __init__(self, content: str | None, tool_calls: list[dict] | None) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.role = "assistant"
        self.function_call = None

    def model_dump(self) -> dict:
        out: dict = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            out["tool_calls"] = self.tool_calls
        return out


class _Choice:
    def __init__(self, message: _Msg) -> None:
        self.message = message
        self.finish_reason = "tool_calls" if message.tool_calls else "stop"


class _Response:
    """Minimal OpenAI ChatCompletion shape satisfying AG2's response protocol."""

    def __init__(self, message: _Msg, model: str) -> None:
        self.choices = [_Choice(message)]
        self.model = model
        self.id = "recette-ag2"
        self.usage = None


def _wrap_response(decision: Any, model: str) -> _Response:
    if decision.is_tool_call:
        tool_calls = [
            {
                "id": "call_0",
                "type": "function",
                "function": {
                    "name": decision.tool_name,
                    "arguments": json.dumps(decision.tool_args or {}, sort_keys=True),
                },
            }
        ]
        return _Response(_Msg(content=None, tool_calls=tool_calls), model)
    return _Response(_Msg(content=decision.text or "", tool_calls=None), model)


def _round_robin(last_speaker: Any, groupchat: Any) -> Any:
    """Deterministic speaker rotation (I4): never asks the LLM to pick (unlike
    AG2's default), so the order is a fixed function of the agent list."""
    agents = groupchat.agents
    idx = agents.index(last_speaker)
    return agents[(idx + 1) % len(agents)]


def _decode_run(team: dict, messages: list[dict]) -> OrchestrationRun:
    """Translate the AG2 group-chat transcript into a recette OrchestrationRun.

    ``order`` is the sequence of genuine speaker turns (AG2 tool-execution result
    turns, role=="tool", are not speaking turns and are dropped). A tool call is
    decoded via a GLOBAL name map and attributed to the agent that actually
    emitted it -- if that agent does not declare the tool, the judge's tool-scope
    check flags it, which is the correct audit outcome (we do not launder it)."""
    participants = {p["agent_id"]: p for p in team["participants"]}
    # Global map: any declared tool name -> (tool_kind, target), regardless of owner.
    global_meta: _ToolMeta = {}
    for p in participants.values():
        global_meta.update(_agent_tool_specs(p)[1])
    order: list[str] = []
    calls: list[ToolCall] = []
    seq = 0
    for m in messages:
        name = m.get("name")
        if name not in participants or m.get("role") == "tool":
            continue
        order.append(name)
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            route = global_meta.get(fn.get("name", ""))
            if route is None:
                continue
            tool_kind, target = route
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (ValueError, TypeError):
                args = {}
            seq += 1
            ident = participants[name]["declared_identity"]
            calls.append(
                ToolCall(
                    seq=seq,
                    agent_id=name,
                    provider=ident["provider"],
                    model=ident["model"],
                    target=target,
                    tool_kind=tool_kind,
                    approved=bool(args.get("approved", False)),
                )
            )
    return OrchestrationRun(order=order, calls=calls)


def _track_run(
    tracker: SessionTracker, session_id: str, team: dict, messages: list[dict]
) -> None:
    """Record one content-free, chained exchange per speaker turn (systematic).

    instance_id = the speaking participant; peer_id = the group floor
    ('chat_manager'). Bodies are digested by the tracker, never persisted raw."""
    participants = {p["agent_id"] for p in team["participants"]}
    seq = 0
    for m in messages:
        name = m.get("name")
        if name not in participants or m.get("role") == "tool":
            continue
        seq += 1
        action = "tool_call" if m.get("tool_calls") else "speak"
        tracker.record(
            TrackedExchange(
                session_id=session_id,
                instance_id=name,
                peer_id="chat_manager",
                seq=seq,
                action_type=action,
                response={"content": m.get("content") or "", "tool_calls": m.get("tool_calls")},
            )
        )


def drive_ag2(
    team: dict,
    backends: LlmBackend | Mapping[str, LlmBackend],
    *,
    session_id: str | None = None,
    tracker: SessionTracker | None = None,
    max_round: int = _DEFAULT_MAX_ROUND,
) -> OrchestrationRun:
    """Run a group-chat team on the real AG2 runtime, each instance autonomous.

    ``backends`` gives each participant its OWN ``LlmBackend`` when a mapping
    ``{instance_id: backend}`` is passed (true per-instance autonomy: own client,
    own key/provider, isolated context). A single ``LlmBackend`` is a convenience
    that backs every agent through DISTINCT client objects (object isolation; same
    decision source -- use the mapping for real isolation). A mapping must cover
    every participant, else ``ValueError`` (blindé: no silent partial wiring).

    When ``tracker`` is given, a ``session_id`` is REQUIRED and one content-free,
    hash-chained exchange is recorded per speaker turn (systematic multi-session
    tracking). Returns the same ``OrchestrationRun`` the native driver yields, so
    the judge, the interaction graph and corpus-freezing consume it unchanged.
    Only the ``group_chat``/``magentic`` styles are served here; the others stay on
    ``recette.orchestrate.drive``.
    """
    style = team.get("style", "handoff")
    if style not in ("group_chat", "magentic"):
        raise NotImplementedError(
            f"drive_ag2 serves the 'group_chat' style; style={style!r} runs on "
            "recette.orchestrate.drive (native driver)"
        )
    if tracker is not None and not session_id:
        raise ValueError("drive_ag2 with a tracker requires a non-empty session_id")

    # Lazy, guarded import: the extra 'ag2' is optional and kept out of the base
    # image (R20/R22), mirroring the pyrit-backed red-team path.
    try:
        from autogen import ConversableAgent, GroupChat, GroupChatManager
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "drive_ag2 requires the optional 'ag2' extra (pip install ia_agent-recette[ag2])"
        ) from exc

    participants = team["participants"]
    if len(participants) < 2:
        raise ValueError("a group chat needs at least two participants")

    # Resolve each instance's OWN backend. A mapping must cover every participant
    # (fail loud on a gap); a single backend backs all, through distinct clients.
    if isinstance(backends, Mapping):
        missing = [p["agent_id"] for p in participants if p["agent_id"] not in backends]
        if missing:
            raise ValueError(f"backends mapping missing an entry for: {', '.join(missing)}")

        def backend_for(pid: str) -> LlmBackend:
            return backends[pid]
    else:
        single = backends

        def backend_for(pid: str) -> LlmBackend:
            return single

    llm_config = {"config_list": [{"model": "recette", "model_client_cls": "RecetteAG2Client"}]}
    agents = []
    for p in participants:
        agent = ConversableAgent(
            name=p["agent_id"],
            system_message=p.get("system_message", _SYSTEM_FALLBACK),
            llm_config=llm_config,
            human_input_mode="NEVER",
            code_execution_config=False,
        )
        # A DISTINCT client per agent (own backend): no shared agent object.
        agent.register_model_client(
            model_client_cls=RecetteAG2Client, backend=backend_for(p["agent_id"])
        )
        agents.append(agent)

    max_turns = team.get("termination", {}).get("max_hops", max_round)
    groupchat = GroupChat(
        agents=agents,
        messages=[],
        max_round=max_turns,
        speaker_selection_method=_round_robin,
    )
    manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)
    # The manager only routes (round-robin, pure); back it with the first agent's
    # backend so it is a real client, never a shared cross-agent instance.
    manager.register_model_client(
        model_client_cls=RecetteAG2Client, backend=backend_for(participants[0]["agent_id"])
    )

    # The first participant opens; kick the chat with a neutral seed so the
    # round-robin then rotates deterministically through the roster.
    agents[0].initiate_chat(manager, message=team.get("seed", "Begin."), clear_history=True)
    run = _decode_run(team, groupchat.messages)
    if tracker is not None and session_id:
        _track_run(tracker, session_id, team, groupchat.messages)
    return run
