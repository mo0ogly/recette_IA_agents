"""Assist copilot endpoints: prompts catalog, operator chat, session memory.

Backs the console's left-rail "Copilote IA" dock and the "Prompts IA" page.

- ``GET/PUT/DELETE /assist/prompts[...]``: the prompt catalog. Defaults live in
  ``recette.api.assist_prompts``; only operator overrides are persisted (in the
  gitignored PromptStore), and ``resolve`` hot-reloads them per call.
- ``POST /assist/chat``: one multi-turn chat exchange through an EXISTING
  ai_backend picked by the console. The server is the only secret resolver
  (R8) and the only prompt assembler (injection guard around any untrusted
  block).
- ``GET/DELETE /assist/sessions/{id}``: read/clear a session's consolidated
  memory (chat thread + insights journal).
- ``GET /assist/topics``: contextual-help grounding topics (populated by the
  help wave; empty catalog until then).

Diagnostic path, NOT a decision path -- I4 does not apply (same documented
stance as POST /config/ai-backends/{id}/test). Failure mode is fail-safe:
every LLM-side error maps to a 200 body with ``source: "error"``; exceptions
never leak to the client as a 500. Unknown backend/prompt ids are the only
404s.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from ...llm import Message, build_llm
from ..assist_prompts import default_catalog, journal_summary, wrap_untrusted
from ..assist_sessions import AssistSession, AssistSessionStore
from ..prompt_store import PromptStore

router = APIRouter(prefix="/assist", tags=["assist"])

# Replay window sent to the model: the last N thread entries BEFORE the new
# user message (the session deque itself keeps the same bound).
CHAT_HISTORY_MESSAGES = 40


def _prompts(request: Request) -> PromptStore:
    return request.app.state.prompt_store


def _sessions(request: Request) -> AssistSessionStore:
    return request.app.state.assist_sessions


def _catalog_entry(entry: dict[str, Any], store: PromptStore) -> dict[str, Any]:
    """Materialize one catalog entry with its resolved value + overridden flag."""
    override = store.get_override(entry["id"])
    return {
        **entry,
        "value": entry["default"] if override is None else override,
        "overridden": override is not None,
    }


@router.get("/prompts")
def list_prompts(request: Request) -> dict:
    store = _prompts(request)
    return {"prompts": [_catalog_entry(entry, store) for entry in default_catalog()]}


@router.put("/prompts/{prompt_id}")
def set_prompt(request: Request, prompt_id: str, body: dict[str, Any]) -> dict:
    """Override one prompt. 404 unknown id; 400 kind mismatch / empty / too big."""
    entry = next((e for e in default_catalog() if e["id"] == prompt_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"no assist prompt {prompt_id!r}")
    value = body.get("value")
    if entry["kind"] == "text":
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(status_code=400, detail="value must be a non-empty string")
    else:  # kind == "json"
        if not isinstance(value, dict | list):
            raise HTTPException(status_code=400, detail="value must be a JSON object or array")
    store = _prompts(request)
    try:
        store.set_override(prompt_id, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _catalog_entry(entry, store)


@router.delete("/prompts/{prompt_id}", status_code=204)
def reset_prompt(request: Request, prompt_id: str) -> Response:
    """Reset one prompt to its default. Idempotent."""
    if prompt_id not in {e["id"] for e in default_catalog()}:
        raise HTTPException(status_code=404, detail=f"no assist prompt {prompt_id!r}")
    _prompts(request).delete_override(prompt_id)
    return Response(status_code=204)


@router.get("/topics")
def list_topics() -> dict:
    """Grounding topics for contextual help. Populated by the help wave."""
    return {"topics": []}


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str) -> dict:
    """The consolidated memory of one session. Unknown id = empty memory."""
    session = _sessions(request).get(session_id)
    if session is None:
        return {"thread": [], "insights": []}
    return {"thread": session.thread_list(), "insights": session.insights_list()}


@router.delete("/sessions/{session_id}", status_code=204)
def clear_session(request: Request, session_id: str) -> Response:
    """Forget one session's chat thread + journal. Idempotent."""
    _sessions(request).clear(session_id)
    return Response(status_code=204)


def _build_system_prompt(request: Request, session: AssistSession) -> str:
    """chat.system (override-aware) + the fenced journal recap when non-empty."""
    store = _prompts(request)
    parts: list[str] = []
    for entry in default_catalog():
        if entry["id"] == "chat.system":
            parts.append(str(store.resolve("chat.system", entry["default"])))
            break
    recap = journal_summary(session.insights_list())
    if recap:
        parts.append(wrap_untrusted(recap, "journal"))
    return "\n\n".join(parts)


@router.post("/chat")
def chat(request: Request, body: dict[str, Any]) -> dict:
    """One chat exchange: append the user turn, call the LLM, append the reply.

    Fail-safe: an LLM error still appends an assistant turn with
    ``source: "error"`` and returns 200, so the dock renders the failure in
    place instead of losing the exchange.
    """
    session_id = body.get("session_id")
    backend_id = body.get("backend_id")
    message = body.get("message")
    if not isinstance(session_id, str) or not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message must be a non-empty string")
    backend = request.app.state.config_store.get_ai_backend(backend_id or "")
    if backend is None:
        raise HTTPException(status_code=404, detail=f"no ai_backend {backend_id!r}")

    session = _sessions(request).get_or_create(session_id)
    system = _build_system_prompt(request, session)
    # History replayed to the model: prior turns only (llm/user), skipping
    # failed assistant turns so an earlier provider error does not pollute the
    # context (same stance as the reference cockpit's bounded replay window).
    history = [
        Message(role=str(m["role"]), content=str(m["content"]))
        for m in session.thread_list()[-CHAT_HISTORY_MESSAGES:]
        if m.get("source") in ("user", "llm")
    ]
    history.append(Message(role="user", content=message))
    session.add_message(role="user", content=message, source="user")

    factory = getattr(request.app.state, "llm_factory", None) or build_llm
    # Per-backend secret first, provider env-var fallback inside the provider
    # classes (R8). The key goes straight to the factory, never logged/returned.
    api_key = request.app.state.secret_store.get_secret(backend["id"])
    model = str(backend.get("model", ""))
    try:
        llm = factory(
            backend["provider"],
            backend["model"],
            base_url=backend.get("base_url"),
            api_key=api_key,
        )
        decision = llm.decide(system=system, history=history, tools=[])
        reply = decision.text
        source = "llm"
        error = None
    except Exception as exc:  # noqa: BLE001 -- fail-safe diagnostic boundary
        reply = ""
        source = "error"
        error = str(exc)
    session.add_message(
        role="assistant",
        content=reply if source == "llm" else f"[erreur backend] {error}",
        source=source,
        model=model if source == "llm" else None,
    )
    return {
        "reply": reply,
        "source": source,
        "model": model if source == "llm" else None,
        "error": error,
        "thread": session.thread_list(),
    }
