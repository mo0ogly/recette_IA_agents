"""U1 config store: one versioned JSON file for Lane B agents + AI backends + servers.

Secrets are never stored (R8) -- AI-backend entries carry only provider + model; the
provider key is resolved from env at run time. Writes are atomic (temp + os.replace).
The file is created lazily on first write; reads of a missing file return the empty default.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SCHEMA_VERSION = "1.0"
_FORBIDDEN_SECRET_FIELDS = {"api_key", "key", "token", "secret", "password", "passwd"}
_RUNTIMES = {"lab", "real"}
_SERVER_MODES = {"mock_local", "declared_url", "real_saas"}
_SERVER_MODE_REQUIRED = {"mock_local": "port", "declared_url": "base_url", "real_saas": "owner"}


class UnknownAgentError(LookupError):
    """Raised when an agent id is not found (maps to HTTP 404, distinct from bad input)."""


class UnknownServerError(LookupError):
    """Raised when a server id is not found (maps to HTTP 404, distinct from bad input)."""


def _check_runtime(runtime: object) -> None:
    if runtime not in _RUNTIMES:
        raise ValueError(f"runtime must be one of {_RUNTIMES}")


def _check_server(server: dict) -> None:
    leaked = _FORBIDDEN_SECRET_FIELDS & set(server)
    if leaked:
        raise ValueError(f"secrets must not be stored (R8): drop {sorted(leaked)}")
    for fname in ("id", "system"):
        value = server.get(fname)
        if not isinstance(value, str) or not value:
            raise ValueError(f"server {fname!r} must be a non-empty string")
    mode = server.get("mode")
    if mode not in _SERVER_MODES:
        raise ValueError(f"server mode must be one of {sorted(_SERVER_MODES)}")
    required = _SERVER_MODE_REQUIRED[mode]
    if required not in server:
        raise ValueError(f"server mode {mode!r} requires field {required!r}")
    if mode == "mock_local" and not (
        isinstance(server["port"], int) and not isinstance(server["port"], bool)
    ):
        raise ValueError("server 'port' must be an integer for mode 'mock_local'")


def _default() -> dict:
    return {"schema_version": SCHEMA_VERSION, "agents": [], "ai_backends": [], "servers": []}


def default_config_path() -> Path:
    env = os.environ.get("AGENTRAIL_CONFIG_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "config" / "agentrail.config.json"


class ConfigStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()

    def read(self) -> dict:
        if not self.path.exists():
            return _default()
        cfg = json.loads(self.path.read_text(encoding="utf-8"))
        cfg.setdefault("schema_version", SCHEMA_VERSION)
        cfg.setdefault("agents", [])
        cfg.setdefault("ai_backends", [])
        cfg.setdefault("servers", [])
        return cfg

    def _write(self, cfg: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # --- agents ---
    def get_agent(self, agent_id: str) -> dict | None:
        return next((a for a in self.read()["agents"] if a["id"] == agent_id), None)

    def add_agent(self, agent: dict) -> dict:
        _check_runtime(agent.get("runtime"))
        cfg = self.read()
        if any(a["id"] == agent["id"] for a in cfg["agents"]):
            raise ValueError(f"agent id {agent['id']!r} already exists")
        cfg["agents"].append(agent)
        self._write(cfg)
        return agent

    def update_agent(self, agent_id: str, patch: dict) -> dict:
        if "runtime" in patch:
            _check_runtime(patch["runtime"])  # reject bad input before mutating/writing
        cfg = self.read()
        for a in cfg["agents"]:
            if a["id"] == agent_id:
                a.update(patch)
                self._write(cfg)
                return a
        raise UnknownAgentError(f"no agent {agent_id!r}")

    def delete_agent(self, agent_id: str) -> None:
        cfg = self.read()
        cfg["agents"] = [a for a in cfg["agents"] if a["id"] != agent_id]
        self._write(cfg)

    # --- ai backends ---
    def get_ai_backend(self, backend_id: str) -> dict | None:
        return next((b for b in self.read()["ai_backends"] if b["id"] == backend_id), None)

    def add_ai_backend(self, backend: dict) -> dict:
        leaked = _FORBIDDEN_SECRET_FIELDS & set(backend)
        if leaked:
            raise ValueError(f"secrets must not be stored (R8): drop {sorted(leaked)}")
        cfg = self.read()
        if any(b["id"] == backend["id"] for b in cfg["ai_backends"]):
            raise ValueError(f"ai_backend id {backend['id']!r} already exists")
        cfg["ai_backends"].append(backend)
        self._write(cfg)
        return backend

    def delete_ai_backend(self, backend_id: str) -> None:
        cfg = self.read()
        cfg["ai_backends"] = [b for b in cfg["ai_backends"] if b["id"] != backend_id]
        self._write(cfg)

    # --- servers ---
    def list_servers(self) -> list[dict]:
        return self.read()["servers"]

    def get_server(self, server_id: str) -> dict | None:
        return next((s for s in self.read()["servers"] if s["id"] == server_id), None)

    def add_server(self, server: dict) -> dict:
        _check_server(server)
        cfg = self.read()
        if any(s["id"] == server["id"] for s in cfg["servers"]):
            raise ValueError(f"server id {server['id']!r} already exists")
        cfg["servers"].append(server)
        self._write(cfg)
        return server

    def update_server(self, server_id: str, patch: dict) -> dict:
        cfg = self.read()
        for i, s in enumerate(cfg["servers"]):
            if s["id"] == server_id:
                merged = {**s, **patch}
                _check_server(merged)  # reject bad input before mutating/writing
                cfg["servers"][i] = merged
                self._write(cfg)
                return merged
        raise UnknownServerError(f"no server {server_id!r}")

    def delete_server(self, server_id: str) -> None:
        cfg = self.read()
        kept = [s for s in cfg["servers"] if s["id"] != server_id]
        if len(kept) == len(cfg["servers"]):
            raise UnknownServerError(f"no server {server_id!r}")
        cfg["servers"] = kept
        self._write(cfg)
