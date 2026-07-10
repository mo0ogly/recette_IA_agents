"""Google Gemini generateContent wire backend."""

from __future__ import annotations

import os

from .._http_client import StdlibHttpClient
from ._core import LlmDecision, Message, ToolSpec, _PostClient


def _to_gemini_contents(history: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in history:
        if m.role == "assistant":
            out.append({"role": "model", "parts": [{"text": m.content}]})
        elif m.role == "tool":
            text = f"[tool {m.tool_name} result] {m.content}"
            out.append({"role": "user", "parts": [{"text": text}]})
        else:
            out.append({"role": "user", "parts": [{"text": m.content}]})
    return out


def _parse_gemini(data: dict) -> LlmDecision:
    candidates = data.get("candidates") or []
    if not candidates:
        return LlmDecision(kind="final", text="", raw=data)
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        call = part.get("functionCall")
        if call:
            return LlmDecision(
                kind="tool_call",
                tool_name=call.get("name"),
                tool_args=call.get("args", {}) or {},
                text="".join(text_parts),
                raw=data,
            )
        if "text" in part:
            text_parts.append(part.get("text", ""))
    return LlmDecision(kind="final", text="".join(text_parts), raw=data)


class GeminiLlm:
    """Google Gemini backend -- generateContent wire format. Key: GEMINI_API_KEY."""

    BASE_URL = "https://generativelanguage.googleapis.com"

    def __init__(
        self,
        *,
        model: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self._model = model
        if client is None:
            key = api_key or os.environ.get("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY not set (or pass client/api_key)")
            client = StdlibHttpClient(
                self.BASE_URL, headers={"x-goog-api-key": key}, proxy_url=proxy_url
            )
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body: dict = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": _to_gemini_contents(history),
        }
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": t.parameters}
                        for t in tools
                    ]
                }
            ]
        resp = self._client.post(f"/v1beta/models/{self._model}:generateContent", json=body)
        resp.raise_for_status()
        return _parse_gemini(resp.json())
