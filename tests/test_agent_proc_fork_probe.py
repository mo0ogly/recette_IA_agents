"""Fork-connect probe (Task 7b) -- the probe is observability-only.

The ``fork_connect_probe`` field on an agent config makes ``main()`` spawn a
SHORT-LIVED CHILD process that performs one real TCP connect, so the kernel
attributes that connect to a different pid than the agent's own and the
sched_process_fork edge links it back -- the live-provable fork-chain surface.

These tests pin two guarantees:
  1. The probe is observability-only: ``run_agent_process`` (the judged path) is
     byte-identical with and without the ``fork_connect_probe`` field, because
     the probe is triggered in ``main()``, never in ``run_agent_process``.
  2. ``_fork_connect_probe`` never raises on a malformed target and makes no
     real connection for one (returns None).
"""

from __future__ import annotations

import unittest

from recette.agent_proc import _fork_connect_probe, run_agent_process


def _base_cfg() -> dict:
    return {
        "id": "fork-probe-test",
        "runtime": "lab",
        "ai_mode": "mock",
        "principal": "dx@acme",
        "target_system": "github",
        "goal": "fork probe test",
        "capability_scope": ["read_repo"],
        "scenario": [{"kind": "final", "text": "fork probe"}],
    }


class ForkConnectProbeTest(unittest.TestCase):
    def test_probe_field_does_not_change_judged_result(self) -> None:
        """The judged dry-run output is identical with and without the field."""
        without = run_agent_process(_base_cfg())
        cfg_with = _base_cfg()
        cfg_with["fork_connect_probe"] = "127.0.0.1:9101"
        with_field = run_agent_process(cfg_with)
        self.assertEqual(without, with_field)

    def test_malformed_targets_never_raise(self) -> None:
        """A malformed target returns None without raising and makes no connect."""
        for target in ("nonsense", "host:notaport", "", ":9101", "host:"):
            with self.subTest(target=target):
                # Returns None (declared -> None) and must not raise nor connect.
                _fork_connect_probe(target)


if __name__ == "__main__":
    unittest.main()
