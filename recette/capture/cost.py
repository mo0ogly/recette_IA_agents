"""Config-driven LLM cost for captured traces (the optional enrichment).

A captured ``LlmCallTrace`` carries ``prompt_tokens`` / ``completion_tokens`` /
``model``. This module turns those tokens into a monetary cost using a pricing
table that is supplied ENTIRELY by configuration -- there are NO hardcoded prices
anywhere (R5 / secrets-source-of-truth). The table is a JSON file whose path is
the env var ``INSPECT_IA_AGENTS_LLM_PRICING_PATH``:

    {
      "llama-3.3-70b-versatile": {"prompt_per_1k": 0.59, "completion_per_1k": 0.79},
      ...
    }

Failure modes (fail-safe, never raise into the capture path):
- env var unset / file missing / unreadable / bad JSON -> EMPTY table (logged),
  so every cost becomes ``None`` ("no price known"), never a guessed number.
- model absent from the table -> cost ``None`` (NOT ``0.0``; zero would be a lie).

Determinism (I4): cost is a PURE function of ``(trace, table)`` -- no clock, no
random, no I/O once the table is loaded. The table itself is loaded once at the
edge (``load_pricing_table``), then mapped over traces.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable

from .llm_trace import LlmCallTrace

#: Env var holding the path to the JSON pricing table (R5: config, never hardcoded).
PRICING_PATH_ENV = "INSPECT_IA_AGENTS_LLM_PRICING_PATH"

#: A pricing table: model -> {"prompt_per_1k": float, "completion_per_1k": float}.
PricingTable = dict[str, dict[str, float]]

_logger = logging.getLogger(__name__)


def _coerce_entry(model: str, entry: object) -> dict[str, float] | None:
    """Return a normalised ``{prompt_per_1k, completion_per_1k}`` or ``None``.

    A malformed entry is dropped (not fatal): a partial table still prices the
    models it does describe, and an undescribed model falls through to ``None``.
    """
    if not isinstance(entry, dict):
        _logger.warning("pricing entry for %r is not an object; dropping", model)
        return None
    try:
        prompt = float(entry["prompt_per_1k"])
        completion = float(entry["completion_per_1k"])
    except (KeyError, TypeError, ValueError):
        _logger.warning("pricing entry for %r is missing/invalid rates; dropping", model)
        return None
    return {"prompt_per_1k": prompt, "completion_per_1k": completion}


def load_pricing_table(path: str | None = None) -> PricingTable:
    """Load the pricing table from ``path`` (default: ``$PRICING_PATH_ENV``).

    Fail-safe: an unset env var, a missing/unreadable file, or invalid JSON all
    yield an EMPTY table (logged at WARNING/INFO), never an exception. With an
    empty table every cost is ``None`` -- the system never invents a price.
    """
    resolved = path if path is not None else os.environ.get(PRICING_PATH_ENV)
    if not resolved:
        _logger.info("%s unset; LLM cost disabled (cost stays None)", PRICING_PATH_ENV)
        return {}
    try:
        with open(resolved, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        _logger.warning("pricing table %r not found; LLM cost disabled", resolved)
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("pricing table %r unreadable/invalid: %s; LLM cost disabled", resolved, exc)
        return {}
    if not isinstance(data, dict):
        _logger.warning("pricing table %r is not a JSON object; LLM cost disabled", resolved)
        return {}
    table: PricingTable = {}
    for model, entry in data.items():
        normalised = _coerce_entry(str(model), entry)
        if normalised is not None:
            table[str(model)] = normalised
    return table


def cost_of(trace: LlmCallTrace, table: PricingTable) -> float | None:
    """Return the monetary cost of ``trace`` under ``table``, or ``None``.

    ``None`` when the trace's model is absent from the table (no price known).
    Otherwise ``prompt_tokens/1000 * prompt_per_1k + completion_tokens/1000 *
    completion_per_1k``. Pure and deterministic.
    """
    rates = table.get(trace.model)
    if rates is None:
        return None
    return (
        trace.prompt_tokens / 1000.0 * rates["prompt_per_1k"]
        + trace.completion_tokens / 1000.0 * rates["completion_per_1k"]
    )


def traces_with_cost(
    traces: Iterable[LlmCallTrace], table: PricingTable | None = None
) -> list[dict]:
    """Serialise ``traces`` to dicts, each carrying a ``cost`` field.

    Convenience for a consumer that wants priced traces in one call: loads the
    configured table once (when ``table`` is ``None``) and maps ``to_dict`` with
    it. With no pricing configured every ``cost`` is ``None`` -- the dicts stay
    valid, the cost is simply unknown.
    """
    resolved = load_pricing_table() if table is None else table
    return [trace.to_dict(pricing=resolved) for trace in traces]
