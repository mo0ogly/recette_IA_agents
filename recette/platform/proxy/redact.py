"""Best-effort secret redaction for the console-facing DEBUG VIEW only.

The proxy debug consoles (``GET /proxy/wire``, ``GET /proxy/traces``) surface
raw request/response bodies so an operator can read what crossed the boundary.
Those bodies can carry tokens. This module masks known secret SHAPES (Bearer
tokens, GitHub/OpenAI/Slack/AWS keys, ``key=value`` secrets) before the view is
emitted, so the debug console does not leak credentials.

This is pattern-based best effort, NOT a guarantee: an unrecognized secret shape
slips through. The content-free context receipts remain the crypto-grade privacy
path (they never expose bodies at all). The append-only audit log is NEVER
redacted (I1): redaction transforms the emitted VIEW dicts only, never the
recorded WireFlow/ProxyTrace objects or the event store. The ``side_effect_hash``
integrity value is preserved by the caller (never redacted).
"""

from __future__ import annotations

import os
import re

MASK = "***REDACTED***"

# Compiled (pattern, replacement) pairs applied in order to a text blob.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Authorization: Bearer <token> -- keep the scheme, mask the credential.
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"), f"Bearer {MASK}"),
    # GitHub tokens: personal (ghp_), oauth (gho_), server (ghs_), user (ghu_).
    (re.compile(r"gh[posu]_[A-Za-z0-9]{16,}"), MASK),
    # OpenAI-style secret keys.
    (re.compile(r"sk-[A-Za-z0-9]{16,}"), MASK),
    # Slack tokens (bot/app/user/refresh/legacy).
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]+"), MASK),
    # AWS access key id.
    (re.compile(r"AKIA[0-9A-Z]{16}"), MASK),
    # Quoted JSON-ish key:value or key=value secret -- keep key + quotes, mask value.
    (
        re.compile(
            r'("?(?:api[_-]?key|token|secret|password|access[_-]?token)"?\s*[:=]\s*")[^"]+(")',
            re.IGNORECASE,
        ),
        rf"\1{MASK}\2",
    ),
    # Unquoted key=value secret -- mask up to the next whitespace or ampersand.
    (
        re.compile(
            r"((?:api[_-]?key|token|secret|password|access[_-]?token)\s*=\s*)[^\s&]+",
            re.IGNORECASE,
        ),
        rf"\1{MASK}",
    ),
    # Unquoted key:value secret (colon form, no quotes) -- keep the key, mask the
    # value up to the next whitespace, comma, or closing brace. This is the
    # YAML/log-line shape (``api_key: myvalue``) the quoted/equals patterns miss.
    # Naturally idempotent: re-running over ``api_key: ***REDACTED***`` recaptures
    # the mask and replaces it with itself.
    (
        re.compile(
            r"((?:api[_-]?key|token|secret|password|access[_-]?token)\s*:\s*)"
            r'([^\s,"}]+)',
            re.IGNORECASE,
        ),
        rf"\1{MASK}",
    ),
]


def redact_text(s: str) -> str:
    """Mask every known secret shape in ``s`` (best effort, pure)."""
    for pattern, replacement in _PATTERNS:
        s = pattern.sub(replacement, s)
    return s


def redact_mapping(obj: object) -> object:
    """Recursively redact a JSON-like structure, returning a NEW structure.

    ``dict`` -> a new dict with redacted values; ``list`` -> a new list; ``str``
    -> ``redact_text``; any other scalar is returned unchanged. The input is
    never mutated.
    """
    if isinstance(obj, dict):
        return {k: redact_mapping(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_mapping(v) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def redaction_enabled() -> bool:
    """Whether console-view redaction is active (default ON, fail-safe)."""
    raw = os.environ.get("INSPECT_IA_AGENTS_PROXY_REDACT", "on").strip().lower()
    return raw not in {"0", "false", "no", "off"}
