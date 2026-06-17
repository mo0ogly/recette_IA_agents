"""U1 config store: one versioned JSON file for Lane B agents + AI backends + servers.

Secrets are never stored (R8) -- AI-backend entries carry only provider + model; the
provider key is resolved from env at run time. Writes are atomic (temp + os.replace).
The file is created lazily on first write; reads of a missing file return the empty default.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SCHEMA_VERSION = "1.0"
_FORBIDDEN_SECRET_FIELDS = {"api_key", "key", "token", "secret", "password", "passwd"}
_RUNTIMES = {"lab", "real"}
# "honeypot" reuses the port-bound mock_server shape but is a SINK an agent must
# never reach through the mediated path; build_allowlist excludes it, so any wire
# flow to it is a bypass signal (ghost-agent / shadow-AI), not a mediated target.
_SERVER_MODES = {"mock_local", "honeypot", "declared_url", "real_saas"}
_PORT_BOUND_MODES = {"mock_local", "honeypot"}
_SERVER_MODE_REQUIRED = {
    "mock_local": "port",
    "honeypot": "port",
    "declared_url": "base_url",
    "real_saas": "owner",
}
# Field names align with corpus/schemas/ground-truth.schema.json: "detectable"
# (expected_discovery.detectable), "expected_verdict" (correct|incorrect) and the
# 4 correctness dimensions of expected_identification.
_GROUND_TRUTH_KEYS = {"detectable", "expected_identity", "dimensions", "expected_verdict"}
_GROUND_TRUTH_DIMENSIONS = {"identity", "capabilities", "policy", "behavior"}
_VERDICTS = {"correct", "incorrect"}


class UnknownAgentError(LookupError):
    """Raised when an agent id is not found (maps to HTTP 404, distinct from bad input)."""


class UnknownServerError(LookupError):
    """Raised when a server id is not found (maps to HTTP 404, distinct from bad input)."""


class ServerNetnameError(ValueError):
    """Raised when a server fqdn/alias is malformed or collides with another server.

    Subclasses ValueError so existing ``except ValueError`` handlers still catch
    it; the config router catches it FIRST to map a netname problem to HTTP 422
    (semantic validation failure), while a plain ValueError (e.g. duplicate id)
    stays HTTP 400 (bad request).
    """


def _check_runtime(runtime: object) -> None:
    if runtime not in _RUNTIMES:
        raise ValueError(f"runtime must be one of {_RUNTIMES}")


def _check_ground_truth(ground_truth: object) -> None:
    """Validate an optional agent ground_truth block (all fields optional).

    Partial ground truth is allowed (the verdict judge only checks what is
    declared); an empty dict is valid and yields a SKIP verdict downstream.
    """
    if not isinstance(ground_truth, dict):
        raise ValueError("ground_truth must be a dict")
    unknown = set(ground_truth) - _GROUND_TRUTH_KEYS
    if unknown:
        raise ValueError(f"ground_truth has unknown keys: {sorted(unknown)}")
    if "detectable" in ground_truth and not isinstance(ground_truth["detectable"], bool):
        raise ValueError("ground_truth 'detectable' must be a boolean")
    if "expected_verdict" in ground_truth and ground_truth["expected_verdict"] not in _VERDICTS:
        raise ValueError(f"ground_truth 'expected_verdict' must be one of {sorted(_VERDICTS)}")
    if "dimensions" in ground_truth:
        dimensions = ground_truth["dimensions"]
        if not isinstance(dimensions, dict):
            raise ValueError("ground_truth 'dimensions' must be a dict")
        unknown_dims = set(dimensions) - _GROUND_TRUTH_DIMENSIONS
        if unknown_dims:
            raise ValueError(f"ground_truth dimensions has unknown keys: {sorted(unknown_dims)}")
        for dim, expected in dimensions.items():
            if not isinstance(expected, bool):
                raise ValueError(f"ground_truth dimension {dim!r} must be a boolean")


_MEMORY_KEYS = {"enabled", "window"}


def _check_memory(memory: object) -> None:
    """Validate an optional agent bounded-memory block.

    Shape: ``{enabled: bool, window: int >= 1}``. A disabled or absent memory
    means the agent runs with the full conversation context; an enabled memory
    bounds the model's input to a sliding window (the goal + last window-1
    messages). Both fields optional; an empty dict is valid (= disabled).
    """
    if not isinstance(memory, dict):
        raise ValueError("memory must be a dict")
    unknown = set(memory) - _MEMORY_KEYS
    if unknown:
        raise ValueError(f"memory has unknown keys: {sorted(unknown)}")
    if "enabled" in memory and not isinstance(memory["enabled"], bool):
        raise ValueError("memory 'enabled' must be a boolean")
    if "window" in memory:
        window = memory["window"]
        if not isinstance(window, int) or isinstance(window, bool) or window < 1:
            raise ValueError("memory 'window' must be an integer >= 1")


_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"
)


def validate_server_netname(server: dict, *, others: list[dict]) -> None:
    """Validate a server's optional fqdn/aliases.

    Names must be syntactic hostnames and must not collide with any name
    (fqdn or alias) declared by a DIFFERENT server. Fail-safe: raise
    ServerNetnameError (a ValueError subclass the config router maps to HTTP
    422) before persistence. An entry updating itself (same id) does not
    collide with its own previous names.
    """
    names: list[str] = []
    fqdn = server.get("fqdn")
    if fqdn is not None:
        names.append(fqdn)
    # Harden: aliases must be a list (reject malformed config with non-list aliases)
    aliases = server.get("aliases")
    if aliases is not None and not isinstance(aliases, list):
        raise ServerNetnameError(f"aliases must be a list: {aliases!r}")
    names.extend(aliases or [])
    for name in names:
        if not isinstance(name, str) or not _HOSTNAME_RE.match(name):
            raise ServerNetnameError(f"invalid hostname: {name!r}")
    taken: set[str] = set()
    for other in others:
        if other.get("id") == server.get("id"):
            continue
        if other.get("fqdn"):
            taken.add(other["fqdn"])
        # Guard: silently skip malformed other-server aliases (do not poison collision set)
        other_aliases = other.get("aliases")
        if isinstance(other_aliases, list):
            taken.update(other_aliases)
    clash = taken.intersection(names)
    if clash:
        raise ServerNetnameError(f"name already declared by another server: {sorted(clash)}")


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
    if mode in _PORT_BOUND_MODES and not (
        isinstance(server["port"], int) and not isinstance(server["port"], bool)
    ):
        raise ValueError(f"server 'port' must be an integer for mode {mode!r}")


def _default() -> dict:
    return {"schema_version": SCHEMA_VERSION, "agents": [], "ai_backends": [], "servers": []}


def default_config_path() -> Path:
    env = os.environ.get("INSPECT_IA_AGENTS_CONFIG_PATH")
    if env:
        return Path(env)
    root = Path(__file__).resolve().parent.parent.parent
    return root / "config" / "inspect_ia_agents.config.json"


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
        if "ground_truth" in agent:
            _check_ground_truth(agent["ground_truth"])
        if "memory" in agent:
            _check_memory(agent["memory"])
        cfg = self.read()
        if any(a["id"] == agent["id"] for a in cfg["agents"]):
            raise ValueError(f"agent id {agent['id']!r} already exists")
        cfg["agents"].append(agent)
        self._write(cfg)
        return agent

    def update_agent(self, agent_id: str, patch: dict) -> dict:
        if "runtime" in patch:
            _check_runtime(patch["runtime"])  # reject bad input before mutating/writing
        if "ground_truth" in patch:
            # Validate the patch value alone, not the merged entry -- update_agent
            # has always worked patch-only (update_server is the stricter one).
            _check_ground_truth(patch["ground_truth"])
        if "memory" in patch:
            _check_memory(patch["memory"])
        cfg = self.read()
        for a in cfg["agents"]:
            if a["id"] == agent_id:
                a.update(patch)
                self._write(cfg)
                return a
        raise UnknownAgentError(f"no agent {agent_id!r}")

    def delete_agent(self, agent_id: str) -> None:
        cfg = self.read()
        kept = [a for a in cfg["agents"] if a["id"] != agent_id]
        if len(kept) == len(cfg["agents"]):
            raise UnknownAgentError(f"no agent {agent_id!r}")
        cfg["agents"] = kept
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

    # --- containment (private-DNS allowlist gate, Task 6) ---
    def _runtime_state_path(self) -> Path:
        """Sidecar holding mutable OPERATIONAL state, NOT the versioned corpus.

        Derived from the config path so a test ConfigStore(tmp) stays isolated.
        The seed config (agents/servers/backends) is a tracked corpus; toggling
        an operational flag must NOT dirty that versioned file, so runtime state
        lives in a gitignored sibling (``*.runtime.json``).
        """
        return self.path.parent / f"{self.path.stem}.runtime.json"

    def _read_runtime_state(self) -> dict:
        p = self._runtime_state_path()
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def containment_enabled(self) -> bool:
        """Whether the private-DNS CONTAINMENT gate is enforced (fail-safe).

        Sourced from the gitignored runtime-state sidecar (operational state),
        with a fallback to a legacy top-level ``containment`` key in the config
        document for back-compat. BOTH settings BLOCK execution on an undeclared
        server name; they differ only in the signal + audit, never allow-vs-deny:
        - False (default, realism-only): an unknown name is a dangling reference
          and ``resolve_proxy`` raises ``ValueError`` -- the run fails, no audit
          event. Never a silent allow.
        - True (gate enforced): ``resolve_proxy`` raises ``ResolutionDenied`` for
          a name NOT in the server allowlist; the run call-site audits a
          ``resolution_denied`` event (I2/I5) and fails the run. No proxy is
          built, no proxy/HTTP call is made.
        """
        state = self._read_runtime_state()
        if "containment" in state:
            return bool(state["containment"])
        # Back-compat: honour a legacy flag baked into the config document.
        return bool(self.read().get("containment", False))

    def set_containment(self, enabled: bool) -> None:
        """Persist the containment flag to the runtime-state sidecar (atomic).

        Written to the gitignored ``*.runtime.json`` sibling, NEVER the tracked
        config corpus -- a UI toggle must not produce a versioned-file diff. This
        is operational state, not an audited event, so a plain overwrite is
        correct (the event store is untouched, I1 N/A).
        """
        state = self._read_runtime_state()
        state["containment"] = bool(enabled)
        p = self._runtime_state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)

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
        # Reject bad/colliding fqdn/aliases against the other existing servers
        # before persistence (maps to HTTP 422).
        validate_server_netname(server, others=cfg["servers"])
        cfg["servers"].append(server)
        self._write(cfg)
        return server

    def update_server(self, server_id: str, patch: dict) -> dict:
        cfg = self.read()
        for i, s in enumerate(cfg["servers"]):
            if s["id"] == server_id:
                # Merge-patch semantics: a None value clears the key (it is not
                # stored as null); any other value sets it.
                merged = {**s}
                for key, value in patch.items():
                    if value is None:
                        merged.pop(key, None)
                    else:
                        merged[key] = value
                # Switching mode strips the target fields of OTHER modes so no
                # stale field (e.g. a residual port after mock_local ->
                # declared_url) survives. A field explicitly set in this patch
                # is never stripped.
                if "mode" in patch and patch["mode"] != s.get("mode"):
                    keep = _SERVER_MODE_REQUIRED.get(merged.get("mode") or "")
                    for field in set(_SERVER_MODE_REQUIRED.values()):
                        if field != keep and field not in patch:
                            merged.pop(field, None)
                _check_server(merged)  # reject bad input before mutating/writing
                # Validate fqdn/aliases of the merged entry against the OTHER
                # servers (its own id is skipped inside validate_server_netname).
                validate_server_netname(merged, others=cfg["servers"])
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
