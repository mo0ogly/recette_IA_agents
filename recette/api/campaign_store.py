"""Discovery-recette campaign + recording persistence.

A campaign is a named, ordered set of Lane B agent launches that the discovery
team runs on demand. Each step references a configured agent and optionally a
mock stub script (scripted decisions); without a stub the agent's bound
ai_backend drives a live LLM (key from env, R8).

Running a campaign persists one Recording per step (replayable artifact), so a
campaign can be re-run deterministically later via replay. Storage is plain
JSON: the campaign catalogue in one file, recordings as one file each in a
directory. Writes are atomic (temp + os.replace).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..recording import Recording

CAMPAIGN_SCHEMA_VERSION = "1.0"


class UnknownCampaignError(LookupError):
    """Raised when a campaign id is not found (maps to HTTP 404)."""


class UnknownRecordingError(LookupError):
    """Raised when a recording id is not found (maps to HTTP 404)."""


def default_campaigns_path() -> Path:
    env = os.environ.get("INSPECT_IA_AGENTS_CAMPAIGNS_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "config" / "campaigns.json"


def default_recordings_dir() -> Path:
    env = os.environ.get("INSPECT_IA_AGENTS_RECORDINGS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "data" / "recordings"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class CampaignStore:
    """JSON-backed catalogue of campaign definitions."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_campaigns_path()

    def _read(self) -> dict:
        if not self.path.exists():
            return {"schema_version": CAMPAIGN_SCHEMA_VERSION, "campaigns": []}
        cfg = json.loads(self.path.read_text(encoding="utf-8"))
        cfg.setdefault("campaigns", [])
        return cfg

    def list(self) -> list[dict]:
        return self._read()["campaigns"]

    def get(self, campaign_id: str) -> dict | None:
        return next((c for c in self.list() if c["id"] == campaign_id), None)

    def add(self, campaign: dict) -> dict:
        if not campaign.get("id"):
            raise ValueError("campaign id is required")
        cfg = self._read()
        if any(c["id"] == campaign["id"] for c in cfg["campaigns"]):
            raise ValueError(f"campaign {campaign['id']!r} already exists")
        entry = {
            "id": campaign["id"],
            "description": campaign.get("description", ""),
            "steps": campaign.get("steps", []),
        }
        cfg["campaigns"].append(entry)
        _atomic_write(self.path, json.dumps(cfg, indent=2) + "\n")
        return entry

    def delete(self, campaign_id: str) -> None:
        cfg = self._read()
        before = len(cfg["campaigns"])
        cfg["campaigns"] = [c for c in cfg["campaigns"] if c["id"] != campaign_id]
        if len(cfg["campaigns"]) == before:
            raise UnknownCampaignError(campaign_id)
        _atomic_write(self.path, json.dumps(cfg, indent=2) + "\n")


class RecordingStore:
    """Directory-backed store of replayable Lane B recordings."""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.dir = Path(directory) if directory is not None else default_recordings_dir()

    def _path(self, recording_id: str) -> Path:
        # Recording ids are caller-built slugs; reject path traversal.
        if "/" in recording_id or ".." in recording_id:
            raise ValueError("invalid recording id")
        return self.dir / f"{recording_id}.json"

    def save(self, recording_id: str, recording: Recording) -> None:
        path = self._path(recording_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = recording.to_dict()
        payload["recording_id"] = recording_id
        _atomic_write(path, json.dumps(payload, indent=2) + "\n")

    def list(self) -> list[dict]:
        if not self.dir.exists():
            return []
        out: list[dict] = []
        for path in sorted(self.dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(
                {
                    "recording_id": data.get("recording_id", path.stem),
                    "agent_id": data.get("agent_id"),
                    "target_system": data.get("target_system"),
                    "goal": data.get("goal"),
                    "provider": data.get("provider"),
                    "steps": len(data.get("steps", [])),
                }
            )
        return out

    def get(self, recording_id: str) -> Recording:
        path = self._path(recording_id)
        if not path.exists():
            raise UnknownRecordingError(recording_id)
        return Recording.from_dict(json.loads(path.read_text(encoding="utf-8")))
