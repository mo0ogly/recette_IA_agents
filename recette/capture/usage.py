"""Provider-agnostic token-usage extraction from a raw LLM response.

OpenAI/Groq report ``usage.prompt_tokens`` / ``usage.completion_tokens``;
Anthropic reports ``usage.input_tokens`` / ``usage.output_tokens``. This reads
both shapes and is fail-safe: malformed or missing usage yields ``(0, 0)`` rather
than raising (observation must never break the run).
"""

from __future__ import annotations


def _as_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def extract_usage(raw: dict) -> tuple[int, int]:
    """Return ``(prompt_tokens, completion_tokens)`` from a raw provider response."""
    usage = raw.get("usage") if isinstance(raw, dict) else None
    if not isinstance(usage, dict):
        return (0, 0)
    prompt = _as_int(usage.get("prompt_tokens", usage.get("input_tokens", 0)))
    completion = _as_int(usage.get("completion_tokens", usage.get("output_tokens", 0)))
    return (prompt, completion)
