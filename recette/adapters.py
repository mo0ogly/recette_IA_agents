"""Pluggable adapters for the discovery and identification tools, plus reference impls.

The real discovery / identification tools are external and their invocation
interface (CLI, HTTP, event-store) is not fixed yet. The harness depends only on
the `DiscoveryAdapter` / `IdentificationAdapter` protocols. A real tool is wired
by implementing one of these protocols.

The reference adapters here are a CORRECT, deterministic evaluator: they compute
discovery + the 4 identification dimensions from (manifest + action log) alone.
They serve two purposes:
1. Self-check that each corpus agent's ground-truth is internally consistent.
2. A template for what a real tool must produce.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol, runtime_checkable

from .events import ESCALATE_ACTIONS, ActionType, AgentAction, Mode

#: Repo root (recette/ is one level down), used to resolve the corpus trust store.
_REPO_ROOT = Path(__file__).resolve().parents[1]

SPAM_THRESHOLD = 5  # same (action_type, resource) repeated >= this many times = anomaly
SPRAY_THRESHOLD = 5  # same action sprayed across >= this many DISTINCT targets = anomaly


def repeats_beyond_threshold(keys: list[tuple[str, str]], threshold: int = SPAM_THRESHOLD) -> bool:
    """True if any key occurs >= threshold times. Shared spam/anomaly test used by
    the git identification adapter and the MAF judge (behavior dimension)."""
    counts: dict[tuple[str, str], int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= threshold:
            return True
    return False


def sprays_beyond_threshold(
    keys: list[tuple[str, str]], threshold: int = SPRAY_THRESHOLD
) -> bool:
    """True if any action is issued against >= threshold DISTINCT targets (a spray
    anomaly): the same action_type fanned out across many resources -- e.g. an
    agent opening one issue on each of many repos. The exact (action, target)
    repeat test misses this because no single (action, target) pair repeats. Same
    behavior dimension, complementary signal; shared by the git adapter and MAF
    judge. Deterministic (stable set membership, no clock/random)."""
    targets: dict[str, set[str]] = {}
    for action, target in keys:
        seen = targets.setdefault(action, set())
        seen.add(target)
        if len(seen) >= threshold:
            return True
    return False


def behavior_is_anomalous(keys: list[tuple[str, str]]) -> bool:
    """The behavior dimension's anomaly test: an exact (action, target) spam
    repeat OR a same-action spray across many distinct targets. One entry point
    so the git adapter and the MAF judge stay in lockstep."""
    return repeats_beyond_threshold(keys) or sprays_beyond_threshold(keys)


@dataclass
class DiscoveryResult:
    detected: bool
    signals: list[str] = field(default_factory=list)


@dataclass
class CapabilityViolation:
    observed_action: str
    kind: str  # undeclared_action | mode_escalation | out_of_scope_resource
    note: str = ""


@dataclass
class IdentificationResult:
    identity_match: bool
    capabilities_conform: bool
    capability_violations: list[CapabilityViolation]
    policy_compliant: bool
    behavior_expected: bool
    verdict: str  # "correct" | "incorrect"


@runtime_checkable
class DiscoveryAdapter(Protocol):
    def discover(self, action_log: list[AgentAction]) -> DiscoveryResult: ...


@runtime_checkable
class IdentificationAdapter(Protocol):
    def identify(
        self, *, manifest: dict, action_log: list[AgentAction]
    ) -> IdentificationResult: ...


class ReferenceDiscoveryAdapter:
    """Detects an agent as soon as it produced at least one observable action."""

    def discover(self, action_log: list[AgentAction]) -> DiscoveryResult:
        if not action_log:
            return DiscoveryResult(detected=False, signals=[])
        signals = ["api_traffic", "credential_usage", "event_stream"]
        return DiscoveryResult(detected=True, signals=signals)


class ReferenceIdentificationAdapter:
    """Computes the 4 correctness dimensions from the manifest and the action log."""

    def identify(self, *, manifest: dict, action_log: list[AgentAction]) -> IdentificationResult:
        identity_match = self._check_identity(manifest, action_log)
        violations = self._check_capabilities(manifest, action_log)
        capabilities_conform = not violations
        policy_compliant = self._check_policy(action_log)
        behavior_expected = self._check_behavior(action_log)

        correct = identity_match and capabilities_conform and policy_compliant and behavior_expected
        return IdentificationResult(
            identity_match=identity_match,
            capabilities_conform=capabilities_conform,
            capability_violations=violations,
            policy_compliant=policy_compliant,
            behavior_expected=behavior_expected,
            verdict="correct" if correct else "incorrect",
        )

    # --- dimension 1: identity (I3) ---
    @staticmethod
    def _check_identity(manifest: dict, action_log: list[AgentAction]) -> bool:
        declared = manifest["declared_identity"]["principal"]
        return all(a.principal == declared for a in action_log)

    # --- dimension 2: declared vs real capabilities ---
    @staticmethod
    def _check_capabilities(
        manifest: dict, action_log: list[AgentAction]
    ) -> list[CapabilityViolation]:
        scope = manifest["capability_scope"]
        violations: list[CapabilityViolation] = []
        for action in action_log:
            matching = [c for c in scope if c["action"] == action.action_type]
            if not matching:
                violations.append(
                    CapabilityViolation(
                        observed_action=action.action_type,
                        kind="undeclared_action",
                        note=f"action '{action.action_type}' not in declared capability_scope",
                    )
                )
                continue
            # Mode escalation: agent performs a write while every matching grant is read-only.
            declared_write = any(c["mode"] == "write" for c in matching)
            if action.mode == Mode.WRITE.value and not declared_write:
                violations.append(
                    CapabilityViolation(
                        observed_action=action.action_type,
                        kind="mode_escalation",
                        note="write action performed under a read-only declared scope",
                    )
                )
            # Resource scope: at least one matching grant must cover the resource.
            if not any(
                any(fnmatch(action.resource, glob) for glob in c["resources"]) for c in matching
            ):
                violations.append(
                    CapabilityViolation(
                        observed_action=action.action_type,
                        kind="out_of_scope_resource",
                        note=f"resource '{action.resource}' is outside the declared resource globs",
                    )
                )
        return violations

    # --- dimension 3: policy conformance (I6) ---
    @staticmethod
    def _check_policy(action_log: list[AgentAction]) -> bool:
        # Default policy: escalate-class actions must carry an approval. The
        # escalate set is the canonical git vocabulary; a non-git action_type
        # (e.g. an okta/finance lane_b action) has no git escalate rule here, so
        # it is treated as compliant on this axis -- its governance lives in the
        # gateway policy path, not this reference git judge.
        for action in action_log:
            try:
                action_type = ActionType(action.action_type)
            except ValueError:
                continue
            if action_type in ESCALATE_ACTIONS and not action.approved:
                return False
        return True

    # --- dimension 4: behavior ---
    @staticmethod
    def _check_behavior(action_log: list[AgentAction]) -> bool:
        # Anomaly = an exact (action, resource) spam repeat OR the same action
        # sprayed across many distinct resources (see behavior_is_anomalous).
        keys = [(a.action_type, a.resource) for a in action_log]
        return not behavior_is_anomalous(keys)


# ---------------------------------------------------------------------------
# Source-based scanning (Discovery / Enrichment Plane)
#
# The colleague's GitHubScanner reads a repository (code + CI/CD surface) and emits
# discovery_risks rows. The harness depends only on the SourceScanAdapter protocol;
# a real scanner is wired by implementing it (see recette/http_adapter.py). The
# ReferenceSourceScanAdapter below is a deterministic offline oracle: what a correct
# scanner MUST output, derived from the repo content alone.
# ---------------------------------------------------------------------------

# Risk level derived from an action (relative ordering, never an absolute opaque score).
_READONLY_ACTIONS = frozenset({"read_repo", "list_repos", "read_ci"})
_BOUNDED_WRITE_ACTIONS = frozenset({"open_pr", "open_issue", "comment_issue"})
# high blast radius: push, merge_pr, manage_webhook, manage_release, trigger_ci

# Full canonical action vocabulary (used to recognize Temporal activity defs as actions).
_KNOWN_ACTIONS: frozenset[str] = frozenset(a.value for a in ActionType)


@dataclass(frozen=True)
class DiscoveryRisk:
    """One discovered risk -- mirrors the discovery_risks table (arch doc section 7)."""

    canonical_agent_id: str
    action_pattern: str
    target_system: str
    estimated_risk: dict
    generated_policy: str | None = None
    # How the agent declares itself, surfaced by the scanner (never silently trusted):
    #   "present" -> a valid .inspect_ia_agents/manifest.json,
    #   "absent"  -> no manifest anywhere (shadow agent detected via code fallback),
    #   "invalid" -> manifest exists but is unparseable or fails the manifest shape.
    passport_status: str | None = None
    # The signed-passport ATTESTATION axis (orthogonal to passport_status above),
    # mirroring the Rust agent-passport crate verdict over
    # .inspect_ia_agents/passport.json:
    #   "trusted"   -> passport parses AND verify() finds no defect,
    #   "untrusted" -> passport parses but verify() accumulates >= 1 reason,
    #   "unsigned"  -> no passport.json (nothing to attest),
    #   "malformed" -> passport.json present but not parseable as a passport,
    #   None        -> not evaluated (e.g. the [bundle] crypto extra is absent):
    #                  never fabricate "trusted" without the signature check.
    attestation_status: str | None = None


@runtime_checkable
class SourceScanAdapter(Protocol):
    """Register a source (repo), scan it, and read back the discovered risks."""

    def register(self, location: str) -> str: ...
    def scan(self, source_id: str) -> str: ...
    def await_run(self, run_id: str) -> str: ...
    def risks(self, source_id: str) -> list[DiscoveryRisk]: ...


# ---------------------------------------------------------------------------
# Attestation oracle -- pure Python mirror of the Rust `agent-passport` crate.
#
# `attest_passport` reproduces, byte-for-byte on the canonical signing form and
# reason-for-reason on the verdict, the frozen semantics of
# discoveryprobe/agent-passport (lib.rs Passport::from_json, canonical.rs
# canonical_bytes, verify.rs verify + UntrustReason Ord). It is the offline
# ORACLE the equivalence test checks against the compiled `passport verify`.
#
# Determinism (I4): the clock is INJECTED (`now`), never read from the wall
# clock. The Ed25519 verify uses `cryptography` lazily (the optional [bundle]
# extra); without it the oracle RAISES ImportError -- it never fabricates a
# "trusted" verdict from a skipped signature check (fail-safe).
# ---------------------------------------------------------------------------

#: The signed subset of a passport (what canonical_bytes covers), mirroring
#: agent-passport `Claims`: the frozen field set, `spiffe_id` optional.
_PASSPORT_SIGNED_FIELDS: tuple[str, ...] = ("id", "tenant", "delegation", "scope", "exp")
#: Every field a valid passport carries (Claims + the seal), for deny_unknown_fields.
_PASSPORT_REQUIRED_FIELDS: tuple[str, ...] = _PASSPORT_SIGNED_FIELDS + ("signature", "key_id")
_PASSPORT_ALLOWED_FIELDS: frozenset[str] = frozenset(_PASSPORT_REQUIRED_FIELDS) | {"spiffe_id"}

#: Canonical UntrustReason enum order (verify.rs derive(Ord)): reasons are sorted
#: by this index so the emitted verdict is replay-stable (I4), matching Rust.
_UNTRUST_ORDER: dict[str, int] = {
    "bad_signature": 0,
    "expired": 1,
    "empty_delegation": 2,
    "no_human_principal": 3,
    "scope_overreach": 4,
    "unknown_key_id": 5,
    "malformed_field": 6,
}


def _passport_canonical_bytes(passport: dict) -> bytes:
    """The exact bytes the Ed25519 signature covers (mirror agent-passport
    canonical.rs). A JSON object of the SIGNED claim fields only -- id, tenant,
    delegation, scope, exp, and spiffe_id ONLY IF present (omitted, not null) --
    keys in ascending order, compact (no spaces), UTF-8. `sort_keys=True` yields
    the Rust insertion order delegation < exp < id < scope < spiffe_id < tenant."""
    claims = {field: passport[field] for field in _PASSPORT_SIGNED_FIELDS}
    spiffe_id = passport.get("spiffe_id")
    if spiffe_id is not None:
        claims["spiffe_id"] = spiffe_id
    return json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _is_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def _days_in_month(year: int, month: int) -> int:
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if month in (4, 6, 9, 11):
        return 30
    if month == 2:
        return 29 if _is_leap(year) else 28
    return 0


def _days_from_civil(year: int, month: int, day: int) -> int:
    """Howard Hinnant's civil-calendar algorithm (mirror verify.rs)."""
    y = year - 1 if month <= 2 else year
    era = (y if y >= 0 else y - 399) // 400
    year_of_era = y - era * 400
    month_index = (month + 9) % 12
    day_of_year = (153 * month_index + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146_097 + day_of_era - 719_468


def _parse_rfc3339_utc(text: str) -> int | None:
    """Parse an RFC3339 UTC timestamp to whole epoch seconds, or None if malformed.

    Mirrors agent-passport verify.rs Timestamp::parse EXACTLY: `YYYY-MM-DDTHH:MM:SS
    [.fraction]Z`, mandatory `Z`, calendar-validated, fractional seconds parsed but
    truncated toward the second. Non-UTC offsets and a missing `Z` are rejected."""
    if not text.endswith("Z"):
        return None
    body = text[:-1]
    if "T" not in body:
        return None
    date, time = body.split("T", 1)
    date_parts = date.split("-")
    if len(date_parts) != 3 or [len(p) for p in date_parts] != [4, 2, 2]:
        return None
    if "." in time:
        time_main, fraction = time.split(".", 1)
        if not fraction or not fraction.isdigit():
            return None
    else:
        time_main = time
    time_parts = time_main.split(":")
    if len(time_parts) != 3 or [len(p) for p in time_parts] != [2, 2, 2]:
        return None
    if not all(p.isdigit() for p in date_parts + time_parts):
        return None
    year, month, day = (int(p) for p in date_parts)
    hour, minute, second = (int(p) for p in time_parts)
    if not 1 <= month <= 12:
        return None
    if not 1 <= day <= _days_in_month(year, month):
        return None
    if hour > 23 or minute > 59 or second > 59:
        return None
    return _days_from_civil(year, month, day) * 86_400 + hour * 3_600 + minute * 60 + second


def _is_human_principal(entry: str) -> bool:
    """A delegation terminal is human iff it starts with 'human:' or contains '@'
    (email-like) -- the frozen rule from verify.rs is_human_principal."""
    return entry.startswith("human:") or "@" in entry


def _passport_shape_ok(passport: dict) -> bool:
    """Mirror Passport::from_json laxness: required fields present with the right
    type, spiffe_id optional (may be null, treated as absent), NO unknown fields
    (deny_unknown_fields). A dict that fails this is `malformed` (a PARSE failure),
    not a verify-time untrust."""
    if set(passport) - _PASSPORT_ALLOWED_FIELDS:
        return False
    for name in ("id", "tenant", "exp", "signature", "key_id"):
        if not isinstance(passport.get(name), str):
            return False
    for name in ("delegation", "scope"):
        value = passport.get(name)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return False
    spiffe_id = passport.get("spiffe_id")
    if spiffe_id is not None and not isinstance(spiffe_id, str):
        return False
    return True


def _passport_signature_ok(passport: dict, pubkey_hex: str) -> bool:
    """Ed25519-verify the passport signature over the canonical claim bytes.

    Lazy-imports `cryptography` (the [bundle] extra); an absent extra RAISES
    ImportError so the caller SKIPS rather than treating an unverified passport as
    trusted. A bad-hex/short signature or a verify failure returns False (mirrors
    verify.rs: decode_hex -> Signature::from_slice -> verify, any failure -> false)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        signature = bytes.fromhex(passport["signature"])
    except ValueError:
        return False
    try:
        public_key.verify(signature, _passport_canonical_bytes(passport))
    except InvalidSignature:
        return False
    return True


def attest_passport(
    passport: dict | None,
    trust: dict[str, str],
    now: str,
    declared: list[str] | None,
) -> tuple[str, list[dict]]:
    """Offline attestation ORACLE -- pure mirror of Rust `agent-passport::verify`.

    Returns ``(status, reasons)`` where ``status`` is one of
    ``trusted | untrusted | unsigned | malformed`` and ``reasons`` is the list of
    kind-tagged reason dicts (e.g. ``[{"kind": "expired"}]``,
    ``[{"kind": "scope_overreach", "extra": ["push"]}]``) mirroring the Rust
    ``Verdict``/``UntrustReason`` serde. Reasons are sorted by the canonical enum
    order so the verdict is replay-stable (I4).

    - ``passport is None`` (no passport.json) -> ``("unsigned", [])``.
    - present but not parseable as a passport -> ``("malformed", [])`` (a PARSE
      failure, mirroring ``Passport::from_json`` -- NOT a schema-validation gate).
    - parses -> accumulate every applicable defect: signature (``key_id`` absent
      from ``trust`` -> ``unknown_key_id`` and the sig check is SKIPPED; else an
      Ed25519 verify over the canonical claim bytes -> ``bad_signature`` on
      failure), expiry (``exp`` unparseable -> ``malformed_field``; ``exp <= now``
      -> ``expired``), delegation (empty -> ``empty_delegation``; terminal not
      human -> ``no_human_principal``), and -- only when ``declared`` is given --
      scope (declared families absent from ``passport.scope`` -> ``scope_overreach``
      with the sorted ``extra``). ``trusted`` iff no reason accumulated.

    Determinism (I4): ``now`` is the INJECTED clock (RFC3339 UTC string), never the
    wall clock. The Ed25519 verify needs the ``cryptography`` ([bundle]) extra; when
    it is absent this RAISES ``ImportError`` -- it NEVER returns ``trusted`` from a
    skipped signature check."""
    if passport is None:
        return ("unsigned", [])
    if not _passport_shape_ok(passport):
        return ("malformed", [])

    now_epoch = _parse_rfc3339_utc(now)
    if now_epoch is None:
        raise ValueError(f"injected clock is not a valid RFC3339 UTC timestamp: {now!r}")

    reasons: list[dict] = []

    # 1. Signature.
    key_id = passport["key_id"]
    pubkey_hex = trust.get(key_id)
    if pubkey_hex is None:
        reasons.append({"kind": "unknown_key_id"})
    elif not _passport_signature_ok(passport, pubkey_hex):
        reasons.append({"kind": "bad_signature"})

    # 2. Expiry.
    exp_epoch = _parse_rfc3339_utc(passport["exp"])
    if exp_epoch is None:
        reasons.append({"kind": "malformed_field", "field": "exp"})
    elif exp_epoch <= now_epoch:
        reasons.append({"kind": "expired"})

    # 3. Delegation.
    delegation = passport["delegation"]
    if not delegation:
        reasons.append({"kind": "empty_delegation"})
    elif not _is_human_principal(delegation[-1]):
        reasons.append({"kind": "no_human_principal"})

    # 4. Scope (only when a declared set is supplied).
    if declared is not None:
        scope = passport["scope"]
        extra = sorted(family for family in declared if family not in scope)
        if extra:
            reasons.append({"kind": "scope_overreach", "extra": extra})

    if not reasons:
        return ("trusted", [])
    reasons.sort(key=lambda reason: _UNTRUST_ORDER[reason["kind"]])
    return ("untrusted", reasons)


def _manifest_has_shape(manifest: dict) -> bool:
    """A manifest is a valid passport only if it carries agent.identity.principal and a
    non-empty agent.capabilities list. Present-but-broken (e.g. missing agent.identity,
    like gh-invalid-passport) fails this and is classified passport_status="invalid"."""
    agent = manifest.get("agent")
    if not isinstance(agent, dict):
        return False
    identity = agent.get("identity")
    if not isinstance(identity, dict) or not identity.get("principal"):
        return False
    capabilities = agent.get("capabilities")
    return isinstance(capabilities, list) and len(capabilities) > 0


def _action_level(action: str) -> int:
    if action in _READONLY_ACTIONS:
        return 1
    if action in _BOUNDED_WRITE_ACTIONS:
        return 2
    return 3  # high blast radius write


class ReferenceSourceScanAdapter:
    """Offline oracle. Derives the correct risk set from a repo tree on disk.

    Detection signals (in precedence order):
    1. `.inspect_ia_agents/manifest.json` -- ManifestScanner native surface, highest precision.
    2. fallback: an `agent/` directory whose Python imports the `github` SDK.

    All outputs are deterministic (invariant 7): `canonical_agent_id` is a stable hash
    of the agent principal, `estimated_risk.level` is derived from the action set + CI
    permissions, and risks are returned in a stable (action-sorted) order.
    """

    #: Corpus trust store + injected clock defaults (I4). The `now` is a FIXED
    #: reference (never the wall clock), matching the ground-truth notes and the
    #: `passport verify --now` used by the equivalence test.
    _DEFAULT_TRUST = _REPO_ROOT / "corpus" / "keys" / "test-authority.trust.json"
    _DEFAULT_NOW = "2027-01-01T00:00:00Z"

    def __init__(self, *, trust_path: Path | None = None, now: str | None = None) -> None:
        self._sources: dict[str, Path] = {}
        self._risks: dict[str, list[DiscoveryRisk]] = {}
        self._n = 0
        self._now = now or self._DEFAULT_NOW
        path = trust_path if trust_path is not None else self._DEFAULT_TRUST
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self._trust: dict[str, str] = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            self._trust = {}

    def register(self, location: str) -> str:
        self._n += 1
        sid = f"ref-src-{self._n:04d}"
        self._sources[sid] = Path(location)
        return sid

    def scan(self, source_id: str) -> str:
        repo = self._sources[source_id]
        self._risks[source_id] = self._analyze(repo)
        return f"ref-run-{source_id}"

    def await_run(self, run_id: str) -> str:
        return "completed"

    def risks(self, source_id: str) -> list[DiscoveryRisk]:
        return list(self._risks.get(source_id, []))

    # --- analysis ---
    def _analyze(self, repo: Path) -> list[DiscoveryRisk]:
        manifest_path = repo / ".inspect_ia_agents" / "manifest.json"
        if manifest_path.exists():
            manifest = self._load_manifest(manifest_path)
            if manifest is not None and _manifest_has_shape(manifest):
                return self._from_manifest(repo, manifest)
            # Manifest present but unparseable OR missing the required shape
            # (agent.identity / agent.capabilities). Detect the agent via the code
            # fallback but tag every risk passport_status="invalid" -- a broken
            # passport is reported, never silently trusted (mirrors scan.rs: manifest
            # present, Passport::parse fails).
            return self._fallback_risks(repo, "invalid")
        # No manifest anywhere -> shadow agent (absent passport) via the fallback chain.
        return self._fallback_risks(repo, "absent")

    def _fallback_risks(self, repo: Path, passport_status: str) -> list[DiscoveryRisk]:
        """Derive risks from code/temporal/openapi surfaces, tagged with the given
        passport_status. Used for shadow agents (absent) and broken manifests (invalid)."""
        if self._has_temporal_agent_code(repo):
            return self._from_temporal_code(repo, passport_status)
        if (repo / "openapi.json").exists():
            return self._from_openapi(repo, passport_status)
        if self._has_github_agent_code(repo):
            return self._from_code(repo, passport_status)
        return []  # true negative

    @staticmethod
    def _load_manifest(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _from_manifest(self, repo: Path, manifest: dict) -> list[DiscoveryRisk]:
        agent = manifest["agent"]
        principal = agent["identity"]["principal"]
        target = agent["target_system"]
        actions = sorted({cap["action"] for cap in agent["capabilities"]})
        return self._build_risks(repo, principal, target, actions, "present")

    def _from_code(self, repo: Path, passport_status: str = "absent") -> list[DiscoveryRisk]:
        # Minimal code-derived fallback (used only when no manifest is present).
        text = "\n".join(p.read_text(encoding="utf-8") for p in (repo / "agent").rglob("*.py"))
        mapping = {
            "create_pull": "open_pr",
            "merge(": "merge_pr",
            "create_hook": "manage_webhook",
            "update_file": "push",
            "create_file": "push",
            "get_repos": "read_repo",
            "get_workflow_runs": "read_ci",
        }
        actions = sorted({pattern for needle, pattern in mapping.items() if needle in text})
        if not actions:
            return []
        return self._build_risks(repo, repo.parent.name, "github", actions, passport_status)

    def _from_temporal_code(
        self, repo: Path, passport_status: str = "absent"
    ) -> list[DiscoveryRisk]:
        # A Temporal agent = real temporalio code; the scanner reads workflow/activity
        # definitions statically. We parse the source via AST (no import, deterministic):
        # each @activity.defn whose name is a canonical action is a declared capability.
        principal, actions = _parse_temporal_dir(repo)
        if not actions:
            return []  # temporalio code without target-system actions = not an agent
        return self._build_risks(
            repo, principal or repo.parent.name, "temporal", actions, passport_status
        )

    def _from_openapi(self, repo: Path, passport_status: str = "absent") -> list[DiscoveryRisk]:
        # An OpenAPI-described agent declares each capability as an operation whose
        # operationId (or x-inspect_ia_agents-action) is a canonical action. The scanner reads
        # the spec; we parse the JSON statically (deterministic, zero extra dependency).
        spec = json.loads((repo / "openapi.json").read_text(encoding="utf-8"))
        info = spec.get("info", {})
        principal = (
            info.get("x-inspect_ia_agents-principal") or info.get("title") or repo.parent.name
        )
        actions: set[str] = set()
        for operations in spec.get("paths", {}).values():
            if not isinstance(operations, dict):
                continue
            for op in operations.values():
                if not isinstance(op, dict):
                    continue
                action = op.get("operationId") or op.get("x-inspect_ia_agents-action")
                if action in _KNOWN_ACTIONS:
                    actions.add(action)
        if not actions:
            return []  # a plain API with no agent capability = not an agent
        return self._build_risks(repo, principal, "openapi", sorted(actions), passport_status)

    def _build_risks(
        self,
        repo: Path,
        principal: str,
        target: str,
        actions: list[str],
        passport_status: str,
    ) -> list[DiscoveryRisk]:
        canonical = hashlib.sha256(principal.encode("utf-8")).hexdigest()[:16]
        ci_bump = 1 if self._has_broad_ci(repo) else 0
        level = max((_action_level(a) for a in actions), default=0)
        level = min(3, level + ci_bump) if level else 0
        policy = self._policy(principal, actions, level) if level >= 2 else None
        # ATTESTATION axis: verify .inspect_ia_agents/passport.json against the
        # corpus trust store + injected clock, cross-checking the DECLARED action
        # families (so scope_overreach is exercised, matching `passport verify
        # --declared`). Orthogonal to passport_status (the manifest axis) above.
        attestation = self._attest_repo(repo, actions)
        return [
            DiscoveryRisk(
                canonical_agent_id=canonical,
                action_pattern=action,
                target_system=target,
                estimated_risk={"level": level},
                generated_policy=policy,
                passport_status=passport_status,
                attestation_status=attestation,
            )
            for action in actions
        ]

    def _attest_repo(self, repo: Path, declared: list[str]) -> str | None:
        """Attestation verdict for the repo's passport.json (absent -> "unsigned",
        unparseable -> "malformed", else the oracle's trusted/untrusted). `declared`
        is applied as the scope cross-check set. Returns None (not evaluated, never a
        false "trusted") when the [bundle] crypto extra is unavailable."""
        passport_path = repo / ".inspect_ia_agents" / "passport.json"
        if not passport_path.exists():
            return "unsigned"
        try:
            passport = json.loads(passport_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "malformed"
        if not isinstance(passport, dict):
            return "malformed"
        try:
            status, _reasons = attest_passport(passport, self._trust, self._now, declared)
        except ImportError:
            return None  # crypto extra absent: fail-safe, never fabricate "trusted"
        return status

    @staticmethod
    def _has_temporal_agent_code(repo: Path) -> bool:
        for py in repo.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "temporalio" in text and ("@activity.defn" in text or "@workflow.defn" in text):
                return True
        return False

    @staticmethod
    def _has_github_agent_code(repo: Path) -> bool:
        agent_dir = repo / "agent"
        if not agent_dir.is_dir():
            return False
        for py in agent_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "import github" in text or "from github import" in text:
                return True
        return False

    @staticmethod
    def _has_broad_ci(repo: Path) -> bool:
        wf_dir = repo / ".github" / "workflows"
        if not wf_dir.is_dir():
            return False
        for wf in wf_dir.glob("*.yml"):
            if "write-all" in wf.read_text(encoding="utf-8"):
                return True
        return False

    @staticmethod
    def _policy(principal: str, actions: list[str], level: int) -> str:
        # A minimal Rego-style policy bounding the agent to its observed actions.
        allowed = ", ".join(f'"{a}"' for a in actions)
        return (
            "package inspect_ia_agents.discovery\n"
            f"# generated for {principal} (risk level {level})\n"
            f"allowed_actions := {{{allowed}}}\n"
            "default allow := false\n"
            "allow if input.action in allowed_actions\n"
        )


# ---------------------------------------------------------------------------
# Temporal surface: static AST analysis of real temporalio workflow/activity code.
# We never import the corpus modules (no temporalio dependency at recette runtime,
# deterministic): an @activity.defn whose function name is a canonical action is a
# declared capability, and a module-level AGENT_PRINCIPAL string is the identity.
# ---------------------------------------------------------------------------


def _is_activity_defn(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "defn"
            and isinstance(target.value, ast.Name)
            and target.value.id == "activity"
        ):
            return True
    return False


def _module_principal(tree: ast.Module) -> str | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "AGENT_PRINCIPAL" for t in node.targets
        ):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return None


def _parse_temporal_dir(repo: Path) -> tuple[str | None, list[str]]:
    """Return (declared principal, sorted action patterns) from temporalio source."""
    actions: set[str] = set()
    principal: str | None = None
    for py in sorted(repo.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        principal = principal or _module_principal(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name in _KNOWN_ACTIONS
                and _is_activity_defn(node)
            ):
                actions.add(node.name)
    return principal, sorted(actions)
