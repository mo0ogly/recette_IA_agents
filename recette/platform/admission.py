"""Passport admission gate -- the `admit_agent` primitive (Control Plane, I2).

`admit_agent` turns an attestation verdict into an admission DECISION under an
observe/enforce gate. It REUSES the attestation ORACLE
(`recette.adapters.attest_passport`) verbatim -- it never re-implements the
Ed25519 verify, the expiry check, or the scope cross-check. Its only additions
are (1) the observe/enforce gate that maps a `status` to `admitted`, and (2) a
fail-safe wrapper so ANY oracle exception denies-or-observes but NEVER admits as
`trusted` (fail-open is forbidden -- failure-modes.md).

Determinism (I4): `now` is an INJECTED clock (an RFC3339 UTC string INPUT), never
`datetime.now()` read inside this module. `admit_agent` performs NO I/O: the
passport, the trust keyring, and `now` are all inputs. The loaders below
(`load_agent_passport`, `load_trust`) do the disk reads and are fail-safe.

Config (R5): the enforce toggle and the passport directory are read from the
environment via documented constants -- no hardcoded flag or path in the logic.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ..adapters import attest_passport

#: Environment toggle for the admission gate. When it equals ``"enforce"``
#: (case-insensitive, trimmed) the gate DENIES a non-trusted agent; otherwise the
#: gate is in ``observe`` mode (record the verdict, admit regardless). R5.
ENFORCE_ENV = "INSPECT_IA_AGENTS_PASSPORT_ENFORCE"

#: Environment override for the directory holding per-agent passports, one
#: ``<agent_id>.json`` per agent. R5.
PASSPORT_DIR_ENV = "INSPECT_IA_AGENTS_PASSPORT_DIR"

#: Default passport directory used when ``PASSPORT_DIR_ENV`` is unset.
DEFAULT_PASSPORT_DIR = "data/agent_passports"


@dataclass(frozen=True)
class AdmissionVerdict:
    """The admission decision for one agent under the observe/enforce gate.

    ``status`` and ``reasons`` come straight from the attestation oracle
    (``trusted | untrusted | unsigned | malformed`` and its kind-tagged reason
    dicts). ``admitted`` folds the gate in: a ``trusted`` agent is always
    admitted; a non-trusted agent is admitted ONLY in ``observe`` mode. ``mode``
    records which gate applied. Frozen so two verdicts over identical inputs
    compare equal (I4 replay stability).
    """

    status: str
    reasons: list[dict]
    admitted: bool
    mode: str


def admit_agent(
    passport: dict | None,
    declared: list[str] | None,
    trust: dict[str, str],
    now: str,
    enforce: bool,
) -> AdmissionVerdict:
    """Attest ``passport`` and decide admission under the observe/enforce gate.

    Pure decision (no I/O, I4): ``passport``, ``declared``, ``trust`` and ``now``
    are all inputs. Delegates the attestation to
    ``attest_passport(passport, trust, now, declared)`` and wraps the resulting
    ``(status, reasons)`` tuple.

    Fail-safe (never fail-open): the oracle call is guarded; ANY exception (e.g. a
    missing ``cryptography`` extra, an invalid injected clock) collapses to
    ``status="untrusted"`` with ``reasons=[{"kind": "oracle_error"}]`` -- never
    ``trusted``. Admission then follows the same gate: denied in ``enforce``,
    admitted in ``observe``.
    """
    mode = "enforce" if enforce else "observe"
    try:
        status, reasons = attest_passport(passport, trust, now, declared)
    except Exception:  # noqa: BLE001 - fail-safe: any oracle failure denies, never admits trusted
        status, reasons = "untrusted", [{"kind": "oracle_error"}]
    admitted = (status == "trusted") or (not enforce)
    return AdmissionVerdict(status=status, reasons=reasons, admitted=admitted, mode=mode)


def enforce_from_env() -> bool:
    """Return True iff ``ENFORCE_ENV`` is set to ``"enforce"`` (case-insensitive,
    trimmed). Any other value, or unset, means observe mode (fail-safe default:
    the gate does not silently start denying)."""
    return os.environ.get(ENFORCE_ENV, "").strip().lower() == "enforce"


def load_agent_passport(agent_id: str, base_dir: Path | str) -> dict | None:
    """Load ``<base_dir>/<agent_id>.json`` as a passport dict (I/O boundary).

    - File absent -> ``None`` (an unsigned agent -> attestation ``unsigned``).
    - File present and valid JSON -> the parsed value.
    - File present but NOT valid JSON -> ``{}`` (a non-sentinel that
      ``attest_passport`` classifies as ``malformed`` -- an empty dict is a
      passport missing every required field). A present-but-corrupt passport is
      thus reported malformed, never silently treated as absent/unsigned.
    """
    path = Path(base_dir) / f"{agent_id}.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def load_trust(path: Path | str) -> dict[str, str]:
    """Load the trust keyring ``{key_id: pubkey_hex}`` from ``path`` (I/O boundary).

    Fail-safe: a missing/unreadable file or non-dict JSON yields ``{}`` -- an
    empty keyring makes ``attest_passport`` report ``unknown_key_id`` -> untrusted,
    never trusted. Never raises.
    """
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): str(value) for key, value in loaded.items()}
