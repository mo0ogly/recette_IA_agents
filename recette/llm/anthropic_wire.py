"""Anthropic Messages wire backends (Anthropic native + MiniMax compatibles)."""

from __future__ import annotations

import os

from .._http_client import StdlibHttpClient
from ._core import LlmDecision, Message, ToolSpec, _PostClient


def _to_anthropic_messages(history: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in history:
        if m.role == "assistant":
            out.append({"role": "assistant", "content": [{"type": "text", "text": m.content}]})
        elif m.role == "tool":
            text = f"[tool {m.tool_name} result] {m.content}"
            out.append({"role": "user", "content": [{"type": "text", "text": text}]})
        else:
            out.append({"role": "user", "content": [{"type": "text", "text": m.content}]})
    return out


def _parse_anthropic(data: dict) -> LlmDecision:
    text_parts: list[str] = []
    for block in data.get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            return LlmDecision(
                kind="tool_call",
                tool_name=block.get("name"),
                tool_args=block.get("input", {}) or {},
                text="".join(text_parts),
                raw=data,
            )
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    return LlmDecision(kind="final", text="".join(text_parts), raw=data)


class AnthropicLlm:
    BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"
    ENV_KEY = "ANTHROPIC_API_KEY"

    @classmethod
    def _auth_headers(cls, key: str) -> dict:
        """Anthropic native auth: x-api-key plus the dated anthropic-version.

        Subclasses targeting an Anthropic-compatible endpoint with a different
        auth scheme override this (e.g. a bearer Authorization header).
        """
        return {"x-api-key": key, "anthropic-version": cls.API_VERSION}

    def __init__(
        self,
        *,
        model: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        if client is None:
            env_key = type(self).ENV_KEY
            key = api_key or os.environ.get(env_key)
            if not key:
                raise RuntimeError(f"{env_key} not set (or pass client/api_key)")
            client = StdlibHttpClient(type(self).BASE_URL, headers=type(self)._auth_headers(key))
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": _to_anthropic_messages(history),
            "tools": [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ],
        }
        resp = self._client.post("/v1/messages", json=body)
        resp.raise_for_status()
        return _parse_anthropic(resp.json())


class MinimaxLlm(AnthropicLlm):
    """MiniMax -- Anthropic Messages wire at api.minimax.io/anthropic. Key: MINIMAX_API_KEY.

    MiniMax exposes an Anthropic-compatible endpoint (Messages API, dated
    anthropic-version), so it reuses the Anthropic request/response shape and the
    /v1/messages path (effective /anthropic/v1/messages). It differs in auth: the
    key travels in a bearer Authorization header, not Anthropic's x-api-key.
    """

    BASE_URL = "https://api.minimax.io/anthropic"
    ENV_KEY = "MINIMAX_API_KEY"

    @classmethod
    def _auth_headers(cls, key: str) -> dict:
        return {"Authorization": f"Bearer {key}", "anthropic-version": cls.API_VERSION}


class MinimaxCnLlm(MinimaxLlm):
    """MiniMax China -- Anthropic Messages wire at api.minimaxi.com. Key: MINIMAX_CN_API_KEY.

    Same bearer-auth Anthropic-compatible shape as MinimaxLlm, against the China
    host (api.minimaxi.com) with a distinct key.
    """

    BASE_URL = "https://api.minimaxi.com/anthropic"
    ENV_KEY = "MINIMAX_CN_API_KEY"
