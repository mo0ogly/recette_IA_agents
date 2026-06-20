"""The live broker manifest generator: comm_marker = agent_id[:15], pure/sorted."""

from __future__ import annotations

import unittest

from recette.platform.probe.manifest_gen import build_manifest


class ManifestGenTest(unittest.TestCase):
    def test_comm_marker_is_the_agent_id_truncated_to_15(self) -> None:
        m = build_manifest(["pr-bot", "a-very-long-agent-name-over-15"])
        self.assertEqual(m["agents"]["pr-bot"]["comm_marker"], "pr-bot")
        # kernel comm is <= 15 bytes; the marker must respect that to ever match.
        self.assertEqual(
            m["agents"]["a-very-long-agent-name-over-15"]["comm_marker"],
            "a-very-long-age",
        )

    def test_dedup_blank_and_sorted_deterministic(self) -> None:
        a = build_manifest(["b", "a", "b", "", "a"])
        b = build_manifest(["a", "b"])
        self.assertEqual(list(a["agents"]), ["a", "b"])  # sorted, deduped, no blank
        self.assertEqual(a, b)  # deterministic (I4)

    def test_max_duration_carried(self) -> None:
        self.assertEqual(build_manifest(["x"], max_duration_ms=1234)["max_duration_ms"], 1234)

    def test_from_config_builds_watch_list_from_every_agent(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        from recette.platform.probe.manifest_gen import main

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg.json"
            cfg.write_text(
                json.dumps({"agents": [{"id": "pr-bot"}, {"id": "issue-bot"}, {"no_id": 1}]}),
                encoding="utf-8",
            )
            out = Path(tmp) / "manifest.json"
            rc = main(["--from-config", str(cfg), "--out", str(out)])
            self.assertEqual(rc, 0)
            manifest = json.loads(out.read_text(encoding="utf-8"))
        # every agent id with an id becomes a watch-list entry (the one without is skipped)
        self.assertEqual(sorted(manifest["agents"]), ["issue-bot", "pr-bot"])


if __name__ == "__main__":
    unittest.main()
