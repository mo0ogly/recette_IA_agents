"""RestartSafeIdGenerator must mint unique ids under concurrency.

Concurrent runs in the one API process (two campaign launches / parallel Lane B
threads) mint ids from the SINGLE shared generator. The unlocked counter raced
and two threads emitted the same id -> "UNIQUE constraint failed: events.event_id"
and a failed run. This guards the lock fix: N threads minting M ids each yield
N*M DISTINCT, monotone ids.
"""

from __future__ import annotations

import threading
import unittest

try:
    from fastapi.testclient import TestClient  # noqa: F401  (proves the [api] extra)

    from recette.api.app import RestartSafeIdGenerator
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_API = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_API = False


@unittest.skipUnless(_HAS_API, "requires the [api] extra (fastapi)")
class EventIdConcurrencyTest(unittest.TestCase):
    def test_concurrent_next_id_is_unique(self) -> None:
        gen = RestartSafeIdGenerator(InMemoryEventStore())
        threads_n = 16
        per_thread = 500
        out: list[str] = []
        out_lock = threading.Lock()
        barrier = threading.Barrier(threads_n)

        def worker() -> None:
            barrier.wait()  # maximize contention: all start together
            local = [gen.next_id() for _ in range(per_thread)]
            with out_lock:
                out.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(threads_n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(out), threads_n * per_thread)
        # No duplicate id was minted (the bug produced collisions here).
        self.assertEqual(len(set(out)), len(out))
        # Ids stay well-formed and strictly increasing once sorted (monotone base+n).
        nums = sorted(int(i[2:]) for i in out)
        self.assertEqual(nums, list(range(nums[0], nums[0] + len(nums))))


if __name__ == "__main__":
    unittest.main()
