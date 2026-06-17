"""AWS Bedrock Converse wire backend (bearer key, no SDK / SigV4)."""

from __future__ import annotations

import os
import urllib.parse

from .._http_client import StdlibHttpClient
from ._core import LlmDecision, Message, ToolSpec, _PostClient


def _to_converse_messages(history: list[Message]) -> list[dict]:
    """Map the neutral history to Bedrock Converse message blocks.

    Tool results are folded into a text user turn (same simplification as the
    Anthropic mapping) so the wire stays free of toolUseId bookkeeping.
    """
    out: list[dict] = []
    for m in history:
        if m.role == "assistant":
            out.append({"role": "assistant", "content": [{"text": m.content}]})
        elif m.role == "tool":
            text = f"[tool {m.tool_name} result] {m.content}"
            out.append({"role": "user", "content": [{"text": text}]})
        else:
            out.append({"role": "user", "content": [{"text": m.content}]})
    return out


def _parse_converse(data: dict) -> LlmDecision:
    blocks = ((data.get("output") or {}).get("message") or {}).get("content") or []
    text_parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        use = block.get("toolUse")
        if use:
            return LlmDecision(
                kind="tool_call",
                tool_name=use.get("name"),
                tool_args=use.get("input", {}) or {},
                text="".join(text_parts),
                raw=data,
            )
        if "text" in block:
            text_parts.append(block.get("text", ""))
    return LlmDecision(kind="final", text="".join(text_parts), raw=data)


class BedrockLlm:
    """AWS Bedrock backend over the Converse API. Key: AWS_BEARER_TOKEN_BEDROCK.

    Uses a Bedrock API key (bearer Authorization header) against the region
    runtime host, so no AWS SDK / SigV4 signing is needed. The default region is
    us-east-1; pass base_url to target another region's bedrock-runtime host. The
    model id is URL-encoded into the /model/{id}/converse path (model ids carry a
    colon, e.g. anthropic.claude-3-5-sonnet-20240620-v1:0).
    """

    BASE_URL = "https://bedrock-runtime.us-east-1.amazonaws.com"
    ENV_KEY = "AWS_BEARER_TOKEN_BEDROCK"

    def __init__(
        self,
        *,
        model: str,
        client: _PostClient | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        if client is None:
            key = api_key or os.environ.get(self.ENV_KEY)
            if not key:
                raise RuntimeError(f"{self.ENV_KEY} not set (or pass client/api_key)")
            client = StdlibHttpClient(
                base_url or self.BASE_URL, headers={"Authorization": f"Bearer {key}"}
            )
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body: dict = {
            "messages": _to_converse_messages(history),
            "inferenceConfig": {"maxTokens": self._max_tokens},
        }
        if system:
            body["system"] = [{"text": system}]
        if tools:
            body["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": {"json": t.parameters},
                        }
                    }
                    for t in tools
                ]
            }
        path = f"/model/{urllib.parse.quote(self._model, safe='')}/converse"
        resp = self._client.post(path, json=body)
        resp.raise_for_status()
        return _parse_converse(resp.json())
