"""Campaign-level record / replay: a campaign becomes a replayable recette (I4).

Mirrors the orchestration and Lane B recordings: capture the verdict sequence a
campaign produces, then re-submit it and assert it reproduces. Uses a stub HTTP
client (a deterministic gateway) so the machinery is tested offline, no fastapi.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.campaign import (
    CampaignRecording,
    CampaignRunner,
    record_campaign,
    replay_campaign,
)

# A campaign whose actions map to a fixed, deterministic verdict (the real gateway
# is deterministic too -- I4 -- so this faithfully models a replay).
_VERDICTS = {
    "suspend_user": "escalate",
    "list_users": "allow",
    "delete_org": "deny",
}


def _action(action_type: str, resource: str, expect: str) -> dict:
    return {
        "agent_id": "admin",
        "target_system": "okta",
        "action_type": action_type,
        "resource": resource,
        "expect": expect,
    }


DOC = {
    "name": "stub-campaign",
    "agents": [
        {"id": "admin", "runtime": "lab", "role": "identity_admin", "capability_scope": ["okta"]}
    ],
    "actions": [
        _action("list_users", "r1", "allow"),
        _action("suspend_user", "r2", "escalate"),
        _action("delete_org", "r3", "deny"),
    ],
}


class _Resp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict:
        return self._payload


class _StubGateway:
    """Deterministic gateway: a fixed verdict per action_type, plus a chain verify."""

    def __init__(self) -> None:
        self.seq = 0

    def post(self, path: str, json: dict | None = None) -> _Resp:
        if path == "/config/agents":
            return _Resp({"id": (json or {}).get("id")}, status=200)
        body = json or {}
        verdict = _VERDICTS[body["action_type"]]
        self.seq += 1
        return _Resp(
            {
                "verdict": verdict,
                "approval_state": "pending" if verdict == "escalate" else "none",
                "executed": verdict == "allow",
                "event_id": f"evt-{self.seq}",
                "side_effect_hash": None,
            }
        )

    def get(self, path: str) -> _Resp:
        return _Resp({"ok": True, "checked": self.seq})


class TestCampaignReplay(unittest.TestCase):
    def test_record_then_replay_reproduces_verdicts(self) -> None:
        rec = record_campaign(CampaignRunner(_StubGateway()), DOC)
        self.assertEqual([v["verdict"] for v in rec.verdicts], ["allow", "escalate", "deny"])

        # Replay against a fresh gateway: the verdict sequence reproduces (I4).
        report, deterministic = replay_campaign(CampaignRunner(_StubGateway()), rec)
        self.assertTrue(deterministic)
        self.assertTrue(report.ok)

    def test_recording_round_trips_through_disk(self) -> None:
        rec = record_campaign(CampaignRunner(_StubGateway()), DOC)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "campaign.recording.json"
            rec.save(path)
            loaded = CampaignRecording.load(path)
        self.assertEqual(loaded.name, "stub-campaign")
        _, deterministic = replay_campaign(CampaignRunner(_StubGateway()), loaded)
        self.assertTrue(deterministic)

    def test_replay_flags_a_divergent_gateway(self) -> None:
        rec = record_campaign(CampaignRunner(_StubGateway()), DOC)

        class _DriftGateway(_StubGateway):
            def post(self, path: str, json: dict | None = None) -> _Resp:
                resp = super().post(path, json)
                if path == "/actions/execute":
                    resp._payload["verdict"] = "allow"  # gateway changed its mind
                return resp

        _, deterministic = replay_campaign(CampaignRunner(_DriftGateway()), rec)
        self.assertFalse(deterministic)


if __name__ == "__main__":
    unittest.main()
