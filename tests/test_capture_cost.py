"""Config-driven LLM cost: env pricing table -> known cost, fail-safe to None.

Covers: known model priced from a temp table, unset env -> None, unknown model
-> None, bad-JSON / missing file -> None (fail-safe, no raise), and determinism
(same input -> same output). Zero hardcoded prices in the source: every price the
test asserts comes from the temp JSON table it writes.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from recette.capture.cost import (
    PRICING_PATH_ENV,
    cost_of,
    load_pricing_table,
    traces_with_cost,
)
from recette.capture.llm_trace import LlmCallTrace

_MODEL = "llama-3.3-70b-versatile"
# These rates live ONLY in the test's temp table; nothing in source hardcodes a price.
_PROMPT_PER_1K = 0.59
_COMPLETION_PER_1K = 0.79


def _trace(**kw) -> LlmCallTrace:
    base = dict(
        seq=1,
        event_id="LC000001",
        agent_id="a1",
        model=_MODEL,
        kind="tool_call",
        tool_name="read_repo",
        resource="acme/x",
        prompt_tokens=1000,
        completion_tokens=500,
        latency_ms=10,
        error=None,
    )
    base.update(kw)
    return LlmCallTrace(**base)


class _PricingFile:
    """Write a temp pricing JSON and point the env var at it; restore on exit."""

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self._dir = tempfile.TemporaryDirectory()
        self._prev = os.environ.get(PRICING_PATH_ENV)

    def __enter__(self) -> str:
        path = Path(self._dir.name) / "pricing.json"
        if isinstance(self._payload, str):
            path.write_text(self._payload, encoding="utf-8")  # raw (e.g. bad JSON)
        else:
            path.write_text(json.dumps(self._payload), encoding="utf-8")
        os.environ[PRICING_PATH_ENV] = str(path)
        return str(path)

    def __exit__(self, *exc: object) -> None:
        if self._prev is None:
            os.environ.pop(PRICING_PATH_ENV, None)
        else:
            os.environ[PRICING_PATH_ENV] = self._prev
        self._dir.cleanup()


class _NoEnv:
    """Ensure the pricing env var is unset for the duration; restore on exit."""

    def __enter__(self) -> None:
        self._prev = os.environ.pop(PRICING_PATH_ENV, None)

    def __exit__(self, *exc: object) -> None:
        if self._prev is not None:
            os.environ[PRICING_PATH_ENV] = self._prev


_KNOWN_TABLE = {_MODEL: {"prompt_per_1k": _PROMPT_PER_1K, "completion_per_1k": _COMPLETION_PER_1K}}


class TestCostOf(unittest.TestCase):
    def test_known_model_priced_from_table(self) -> None:
        # 1000 prompt + 500 completion at the temp rates.
        expected = 1.0 * _PROMPT_PER_1K + 0.5 * _COMPLETION_PER_1K
        self.assertAlmostEqual(cost_of(_trace(), _KNOWN_TABLE), expected)

    def test_unknown_model_is_none_not_zero(self) -> None:
        self.assertIsNone(cost_of(_trace(model="some-unlisted-model"), _KNOWN_TABLE))

    def test_empty_table_is_none(self) -> None:
        self.assertIsNone(cost_of(_trace(), {}))

    def test_deterministic_same_input_same_output(self) -> None:
        a = cost_of(_trace(), _KNOWN_TABLE)
        b = cost_of(_trace(), _KNOWN_TABLE)
        self.assertEqual(a, b)


class TestLoadPricingTable(unittest.TestCase):
    def test_env_set_loads_table(self) -> None:
        with _PricingFile(_KNOWN_TABLE):
            table = load_pricing_table()
        self.assertEqual(table[_MODEL]["prompt_per_1k"], _PROMPT_PER_1K)

    def test_env_unset_returns_empty_table(self) -> None:
        with _NoEnv():
            self.assertEqual(load_pricing_table(), {})

    def test_missing_file_returns_empty_table(self) -> None:
        with _NoEnv():
            self.assertEqual(load_pricing_table("/nonexistent/dir/pricing.json"), {})

    def test_bad_json_is_fail_safe_no_raise(self) -> None:
        with _PricingFile("{ this is not valid json ]"):
            table = load_pricing_table()  # must not raise
        self.assertEqual(table, {})

    def test_non_object_json_returns_empty_table(self) -> None:
        with _PricingFile([1, 2, 3]):
            self.assertEqual(load_pricing_table(), {})

    def test_malformed_entry_is_dropped_others_kept(self) -> None:
        payload = {
            _MODEL: {"prompt_per_1k": _PROMPT_PER_1K, "completion_per_1k": _COMPLETION_PER_1K},
            "broken-model": {"prompt_per_1k": "not-a-number"},
        }
        with _PricingFile(payload):
            table = load_pricing_table()
        self.assertIn(_MODEL, table)
        self.assertNotIn("broken-model", table)


class TestEnvEndToEnd(unittest.TestCase):
    def test_env_set_yields_known_cost(self) -> None:
        with _PricingFile(_KNOWN_TABLE):
            expected = 1.0 * _PROMPT_PER_1K + 0.5 * _COMPLETION_PER_1K
            self.assertAlmostEqual(cost_of(_trace(), load_pricing_table()), expected)

    def test_env_unset_yields_none_cost(self) -> None:
        with _NoEnv():
            self.assertIsNone(cost_of(_trace(), load_pricing_table()))

    def test_unknown_model_under_real_table_is_none(self) -> None:
        with _PricingFile(_KNOWN_TABLE):
            table = load_pricing_table()
        self.assertIsNone(cost_of(_trace(model="unlisted"), table))


class TestToDictBackwardCompat(unittest.TestCase):
    def test_no_pricing_arg_has_no_cost_key(self) -> None:
        self.assertNotIn("cost", _trace().to_dict())

    def test_pricing_table_adds_cost_field(self) -> None:
        d = _trace().to_dict(pricing=_KNOWN_TABLE)
        expected = 1.0 * _PROMPT_PER_1K + 0.5 * _COMPLETION_PER_1K
        self.assertAlmostEqual(d["cost"], expected)

    def test_pricing_table_unknown_model_cost_is_none(self) -> None:
        d = _trace(model="unlisted").to_dict(pricing=_KNOWN_TABLE)
        self.assertIsNone(d["cost"])

    def test_empty_pricing_table_still_adds_cost_key_as_none(self) -> None:
        d = _trace().to_dict(pricing={})
        self.assertIn("cost", d)
        self.assertIsNone(d["cost"])


class TestTracesWithCost(unittest.TestCase):
    def test_explicit_table_prices_each_trace(self) -> None:
        traces = [_trace(seq=1), _trace(seq=2, model="unlisted")]
        out = traces_with_cost(traces, _KNOWN_TABLE)
        expected = 1.0 * _PROMPT_PER_1K + 0.5 * _COMPLETION_PER_1K
        self.assertAlmostEqual(out[0]["cost"], expected)
        self.assertIsNone(out[1]["cost"])

    def test_loads_configured_table_when_none(self) -> None:
        with _PricingFile(_KNOWN_TABLE):
            out = traces_with_cost([_trace()])
        expected = 1.0 * _PROMPT_PER_1K + 0.5 * _COMPLETION_PER_1K
        self.assertAlmostEqual(out[0]["cost"], expected)

    def test_no_env_yields_none_cost_per_trace(self) -> None:
        with _NoEnv():
            out = traces_with_cost([_trace()])
        self.assertIsNone(out[0]["cost"])


if __name__ == "__main__":
    unittest.main()
