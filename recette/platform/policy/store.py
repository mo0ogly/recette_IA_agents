"""PolicyStore: append-only versioned JSON documents on disk.

One file per version under the policies directory, never rewritten (I1).
The active version is a separate small pointer file; switching the active
version never mutates a published document.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .model import PolicyVersion


class UnknownPolicyVersionError(LookupError):
    """Raised when a version id is not found (maps to HTTP 404)."""


def default_policies_dir() -> Path:
    env = os.environ.get("AGENTRAIL_POLICIES_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "config" / "policies"


class PolicyStore:
    def __init__(self, directory: Path | str | None = None) -> None:
        self._dir = Path(directory) if directory is not None else default_policies_dir()
        self._active_file = self._dir / "active.json"

    def _version_path(self, version: str) -> Path:
        safe = version.replace("/", "_")
        return self._dir / f"policy.{safe}.json"

    def list_versions(self) -> list[str]:
        if not self._dir.exists():
            return []
        versions = []
        for path in sorted(self._dir.glob("policy.*.json")):
            versions.append(path.name[len("policy.") : -len(".json")])
        return versions

    def get(self, version: str) -> PolicyVersion:
        path = self._version_path(version)
        if not path.exists():
            raise UnknownPolicyVersionError(f"no policy version {version!r}")
        return PolicyVersion.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def publish(self, policy: PolicyVersion) -> PolicyVersion:
        """Write a new immutable version. Refuses to overwrite an existing one (I1)."""
        path = self._version_path(policy.version)
        if path.exists():
            raise ValueError(f"policy version {policy.version!r} already published (immutable)")
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(policy.to_dict(), indent=2, sort_keys=True) + "\n", "utf-8")
        os.replace(tmp, path)
        if not self._active_file.exists():
            self.set_active(policy.version)
        return policy

    def set_active(self, version: str) -> None:
        if not self._version_path(version).exists():
            raise UnknownPolicyVersionError(f"no policy version {version!r}")
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._active_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"active": version}) + "\n", encoding="utf-8")
        os.replace(tmp, self._active_file)

    def active_version_id(self) -> str | None:
        if not self._active_file.exists():
            return None
        return json.loads(self._active_file.read_text(encoding="utf-8"))["active"]

    def active(self) -> PolicyVersion:
        """Return the active policy. No active policy is a hard error: the
        gateway must fail closed rather than guess a policy."""
        version = self.active_version_id()
        if version is None:
            raise UnknownPolicyVersionError("no active policy version configured")
        return self.get(version)
