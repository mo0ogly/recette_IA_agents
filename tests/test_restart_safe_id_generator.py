"""Regression for the API event-id generator (recette/api/app.py).

The governed path appends one event per agent action; once campaigns are routed
through the gateway it mints MANY ids per run. A base derived only from the log
count realigns onto an already-persisted id when the log grew with a variable
number of appends per process -- a UNIQUE-constraint failure on append (I1 break:
a governed action that cannot be recorded). The generator derives its base
strictly above every persisted id, so a restart can never re-mint one.
"""

from __future__ import annotations

import unittest

try:
    # RestartSafeIdGenerator lives in recette.api.app, which imports fastapi at
    # module level, so collection needs the [api] extra. Guard the import so the
    # suite collects cleanly without it (R20); the test runs where fastapi is.
    from recette.api.app import RestartSafeIdGenerator
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_API = True
except ImportError:  # pragma: no cover - depends on the [api] extra (fastapi)
    _HAS_API = False


def _seed(store: InMemoryEventStore, event_id: str) -> None:
    store.append(event_id=event_id, kind="action_executed", payload={}, schema_version="1.0")


@unittest.skipUnless(_HAS_API, "requires the [api] extra (fastapi)")
class TestRestartSafeIdGenerator(unittest.TestCase):
    def test_fresh_store_keeps_the_historical_first_id(self) -> None:
        gen = RestartSafeIdGenerator(InMemoryEventStore())
        self.assertEqual(gen.next_id(), f"EV{1_000_001:024d}")

    def test_base_is_strictly_above_a_high_id_low_count_log(self) -> None:
        # One event with a high id: a count-based base alone would re-mint it
        # (the restart-alignment collision). The hardened base clears it.
        store = InMemoryEventStore()
        _seed(store, f"EV{2_000_001:024d}")
        minted = RestartSafeIdGenerator(store).next_id()
        self.assertGreater(int(minted[2:]), 2_000_001)
        # And it actually appends -- no duplicate-id violation (the real failure).
        _seed(store, minted)

    def test_minted_ids_never_collide_across_a_simulated_restart(self) -> None:
        store = InMemoryEventStore()
        # Process A: mint and persist a burst.
        gen_a = RestartSafeIdGenerator(store)
        for _ in range(5):
            _seed(store, gen_a.next_id())
        # Process B (restart over the same store): every id must still append.
        gen_b = RestartSafeIdGenerator(store)
        for _ in range(5):
            _seed(store, gen_b.next_id())  # raises ValueError on a collision
        self.assertEqual(len(store.read_from()), 10)

    def test_sequence_is_deterministic_for_a_given_store_state(self) -> None:
        store = InMemoryEventStore()
        _seed(store, f"EV{5_000_009:024d}")
        a = RestartSafeIdGenerator(store)
        b = RestartSafeIdGenerator(store)
        self.assertEqual([a.next_id() for _ in range(3)], [b.next_id() for _ in range(3)])


if __name__ == "__main__":
    unittest.main()
