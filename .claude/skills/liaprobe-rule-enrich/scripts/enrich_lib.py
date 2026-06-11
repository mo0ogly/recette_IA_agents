"""
enrich_lib -- Shared library for LiaProbe rule enrichment skill v2.

Provides production-grade primitives:
- AtomicJSONWriter        : write JSON atomically (tmp + os.replace + fsync)
- LockManager             : fcntl flock per-rule (concurrency safe)
- StateManager            : per-rule state file + lifecycle + cycles status
- EvidenceWriter          : evidence storage + sha256 + symlink _latest
- SchemaValidator         : jsonschema validation strict
- HTTPClient              : urllib + cache (7d TTL) + retry exp backoff
- PGClient                : psycopg2 wrapper, env-driven DSN
- StructuredLogger        : append-only JSONL audit trail

Design : zero approximation. All operations atomic + verifiable.
See _alire/tracking/liaprobe-enrich-v2/DESIGN.md for architecture.

Conventions :
- All paths absolute Path objects (no string concat)
- All write operations atomic (tmp + replace + fsync)
- All external data hashed sha256 (raw bytes, not normalized)
- All errors raise typed exceptions (no silent swallow)
- Type hints mandatory on public API

Compatibility : Python 3.10+, Linux/macOS (fcntl). Windows not supported.
"""
from __future__ import annotations

import contextlib
import dataclasses
import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ======================================================================
# Exceptions
# ======================================================================

class EnrichError(Exception):
    """Base exception for enrichment library."""
    exit_code = 1


class InvalidInputError(EnrichError):
    """Input file invalid (missing, malformed, schema violation)."""
    exit_code = 2


class DependencyMissingError(EnrichError):
    """External dependency unavailable (PG down, API 5xx, etc.)."""
    exit_code = 3


class LockContentionError(EnrichError):
    """Could not acquire lock within timeout."""
    exit_code = 4


class TamperDetectedError(EnrichError):
    """Evidence sha256 mismatch -- evidence has been tampered with."""
    exit_code = 5


class DriftCriticalError(EnrichError):
    """Source unreachable or shape changed catastrophically."""
    exit_code = 6


# ======================================================================
# Time + checksum helpers
# ======================================================================

def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_iso_compact() -> str:
    """Return UTC time formatted for filenames (no colons): 2026-05-02T14-30-00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def sha256_bytes(data: bytes) -> str:
    """Return hex SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_string(s: str) -> str:
    """Return hex SHA-256 of UTF-8 encoded string."""
    return sha256_bytes(s.encode("utf-8"))


def sha256_canonical_json(obj: Any) -> str:
    """SHA-256 of canonical JSON (sort_keys, no spaces, ensure_ascii)."""
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256_string(canon)


def sha256_file(path: Path) -> str:
    """SHA-256 of file content (read binary)."""
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha1_path(path: str | Path) -> str:
    """SHA-1 of absolute path string (for state file naming)."""
    abs_path = str(Path(path).resolve())
    return hashlib.sha1(abs_path.encode("utf-8")).hexdigest()  # noqa: S324


# ======================================================================
# Atomic JSON writer
# ======================================================================

class AtomicJSONWriter:
    """Write JSON atomically: tmp file + fsync + os.replace.

    Guarantees:
    - On success: target file contains complete new content
    - On crash mid-write: target unchanged, .tmp may exist (cleanable)
    - POSIX rename is atomic on same filesystem
    """

    @staticmethod
    def write(path: Path, data: Any, *, indent: int = 2, ensure_newline: bool = True) -> None:
        """Atomically write JSON-serializable data to path.

        Args:
            path: Target file path (parent must exist).
            data: JSON-serializable Python object.
            indent: JSON indentation (default 2).
            ensure_newline: Append trailing newline (POSIX convention).

        Raises:
            OSError: parent dir missing or permission denied
            TypeError: data not JSON-serializable
        """
        path = Path(path)
        if not path.parent.exists():
            raise OSError(f"Parent directory does not exist: {path.parent}")

        tmp = path.with_suffix(path.suffix + ".tmp")
        # Serialize first to catch errors before opening file
        text = json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=False)
        if ensure_newline and not text.endswith("\n"):
            text += "\n"

        # Write to tmp, fsync, atomic rename
        # Use os.O_WRONLY | O_CREAT | O_TRUNC for direct open
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd, text.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(path))  # atomic POSIX rename

    @staticmethod
    def cleanup_orphan_tmp(path: Path) -> bool:
        """Remove orphan .tmp file from previous crashed write.

        Returns:
            True if .tmp existed and was removed.
        """
        tmp = path.with_suffix(path.suffix + ".tmp")
        if tmp.exists():
            try:
                tmp.unlink()
                return True
            except OSError:
                return False
        return False


# ======================================================================
# Lock manager (fcntl flock)
# ======================================================================

class LockManager:
    """Per-resource exclusive lock via fcntl.flock.

    Linux/macOS only. Lock file remains on disk; it's the file lock that matters.
    """

    DEFAULT_TIMEOUT_S = 30
    POLL_INTERVAL_S = 0.1

    def __init__(self, lock_path: Path, timeout_s: float | None = None):
        self.lock_path = Path(lock_path)
        self.timeout_s = timeout_s if timeout_s is not None else self.DEFAULT_TIMEOUT_S
        self._fd: int | None = None

    def acquire(self) -> None:
        """Acquire exclusive lock. Raises LockContentionError on timeout."""
        if self._fd is not None:
            raise EnrichError("Lock already acquired by this instance")
        if not self.lock_path.parent.exists():
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Open or create lock file
        self._fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o600)

        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Got the lock
                return
            except OSError as e:
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    self._close_fd()
                    raise
                # Would block -- check timeout
                if time.monotonic() >= deadline:
                    self._close_fd()
                    raise LockContentionError(
                        f"Could not acquire lock on {self.lock_path} within {self.timeout_s}s"
                    )
                time.sleep(self.POLL_INTERVAL_S)

    def release(self) -> None:
        """Release lock and close fd."""
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            self._close_fd()

    def _close_fd(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self) -> LockManager:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


# ======================================================================
# Schema validator (jsonschema)
# ======================================================================

# Lia fingerprint schema -- minimal validation (full schema deferred)
LIA_FINGERPRINT_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["$schema", "id", "taxonomy_code", "product"],
    "properties": {
        "$schema": {"type": "string", "const": "lia-fingerprint-v1"},
        "id": {"type": "string", "minLength": 1},
        "taxonomy_code": {"type": "string", "minLength": 1},
        "product": {"type": "string"},
        "vendor": {"type": "string"},
        "cpe23_template": {"type": "string"},
        "default_ports": {"type": "array"},
        "probes": {"type": "array"},
        "banner_matchers": {"type": "array"},
        "service_matchers": {"type": "array"},
    },
    "additionalProperties": True,  # allow enrichment fields
}


LIA_EVIDENCE_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": [
        "$schema", "cycle", "rule", "applied_at", "applied_by",
        "source", "raw_data_sha256", "applied_diff_sha256",
    ],
    "properties": {
        "$schema": {"type": "string", "const": "lia-enrich-evidence-v1"},
        "cycle": {"type": "string", "pattern": r"^\d+_[a-z_]+$"},
        "rule": {
            "type": "object",
            "required": ["id", "path", "rule_sha256"],
        },
        "applied_at": {"type": "string"},
        "applied_by": {"type": "string"},
        "source": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {"enum": ["postgresql", "http", "csv", "manual"]},
            },
        },
        "raw_data_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "applied_diff_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "additionalProperties": True,
}


class SchemaValidator:
    """jsonschema-based validator. Falls back gracefully if jsonschema absent."""

    @staticmethod
    def validate_fingerprint(data: dict) -> None:
        """Validate a LiaProbe fingerprint dict. Raises InvalidInputError on failure."""
        if not HAS_JSONSCHEMA:
            # Fallback minimal validation
            for key in ("$schema", "id", "taxonomy_code"):
                if key not in data:
                    raise InvalidInputError(f"Missing required field: {key}")
            if data.get("$schema") != "lia-fingerprint-v1":
                raise InvalidInputError(
                    f"Schema must be 'lia-fingerprint-v1', got: {data.get('$schema')}"
                )
            return
        try:
            jsonschema.validate(instance=data, schema=LIA_FINGERPRINT_SCHEMA)
        except jsonschema.ValidationError as e:
            raise InvalidInputError(f"Fingerprint schema violation: {e.message}") from e

    @staticmethod
    def validate_evidence(data: dict) -> None:
        """Validate an evidence dict. Raises InvalidInputError on failure."""
        if not HAS_JSONSCHEMA:
            for key in ("$schema", "cycle", "rule", "source", "raw_data_sha256"):
                if key not in data:
                    raise InvalidInputError(f"Missing required evidence field: {key}")
            return
        try:
            jsonschema.validate(instance=data, schema=LIA_EVIDENCE_SCHEMA)
        except jsonschema.ValidationError as e:
            raise InvalidInputError(f"Evidence schema violation: {e.message}") from e


# ======================================================================
# HTTP client (cache + retry)
# ======================================================================

@dataclasses.dataclass(frozen=True)
class HTTPResponse:
    """Captured HTTP response with provenance."""
    url: str
    status: int
    body: bytes
    fetched_at: str  # ISO 8601 UTC
    from_cache: bool
    response_size_bytes: int

    @property
    def body_sha256(self) -> str:
        return sha256_bytes(self.body)


class HTTPClient:
    """HTTP GET client with disk cache + retry exponential backoff.

    - Cache TTL: 7 days default (configurable)
    - Retry: 3 attempts (1s, 2s, 4s backoff) on connection errors / 5xx
    - User-Agent: configurable, default LiaProbe-enrich/v2
    """

    DEFAULT_CACHE_TTL_S = 7 * 24 * 3600
    DEFAULT_TIMEOUT_S = 10
    DEFAULT_USER_AGENT = "LiaProbe-enrich/v2"
    MAX_RETRIES = 3

    def __init__(
        self,
        cache_dir: Path,
        cache_ttl_s: int = DEFAULT_CACHE_TTL_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_s = cache_ttl_s
        self.timeout_s = timeout_s
        self.user_agent = user_agent

    def _cache_path(self, url: str) -> Path:
        """Compute cache file path from URL."""
        key = sha256_string(url)[:16] + "_" + re.sub(r"[^A-Za-z0-9._-]", "_", url)[-80:]
        return self.cache_dir / key

    def _read_cache(self, url: str) -> HTTPResponse | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.cache_ttl_s:
            return None
        try:
            data = path.read_bytes()
            # Cache stores: 4-byte BE int status + body
            if len(data) < 4:
                return None
            status = int.from_bytes(data[:4], "big", signed=False)
            body = data[4:]
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            return HTTPResponse(
                url=url, status=status, body=body,
                fetched_at=mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
                from_cache=True,
                response_size_bytes=len(body),
            )
        except OSError:
            return None

    def _write_cache(self, url: str, status: int, body: bytes) -> None:
        path = self._cache_path(url)
        try:
            with path.open("wb") as fp:
                fp.write(status.to_bytes(4, "big", signed=False))
                fp.write(body)
        except OSError:
            pass  # cache write failure is non-fatal

    def get(self, url: str, *, use_cache: bool = True) -> HTTPResponse:
        """HTTP GET with cache + retry.

        Args:
            url: full URL to fetch
            use_cache: read from cache if available (write always)

        Raises:
            DependencyMissingError: all retries failed
        """
        if use_cache:
            cached = self._read_cache(url)
            if cached is not None:
                return cached

        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": self.user_agent}
                )
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    status = resp.status
                    body = resp.read()
                # Cache only successful responses
                if 200 <= status < 300:
                    self._write_cache(url, status, body)
                return HTTPResponse(
                    url=url, status=status, body=body,
                    fetched_at=utc_now_iso(),
                    from_cache=False,
                    response_size_bytes=len(body),
                )
            except urllib.error.HTTPError as e:
                # 4xx is a deterministic client error (e.g. 404 = slug absent
                # from the catalog). Return the response with its status so the
                # caller can classify it (no_data) instead of burning retries
                # and surfacing it as a generic network failure.
                if 400 <= e.code < 500:
                    try:
                        body = e.read()
                    except OSError:
                        body = b""
                    return HTTPResponse(
                        url=url, status=e.code, body=body,
                        fetched_at=utc_now_iso(),
                        from_cache=False,
                        response_size_bytes=len(body),
                    )
                # 5xx is transient: retry with backoff.
                last_exc = e
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_exc = e
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s
        raise DependencyMissingError(
            f"HTTP GET failed after {self.MAX_RETRIES} attempts: {url} -- {last_exc}"
        )


# ======================================================================
# PostgreSQL client (psycopg2)
# ======================================================================

class PGClient:
    """PostgreSQL query wrapper.

    DSN resolution order:
    1. Explicit dsn= parameter
    2. DATABASE_URL env var
    3. LIA_DB_* env vars (LIA_DB_HOST, LIA_DB_PORT, LIA_DB_NAME, LIA_DB_USER, LIA_DB_PASS)
    4. Standard PG* env vars (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD)
    5. systemd unit fallback: `systemctl cat lia-backend` Environment=DATABASE_URL
       (so an interactive session needs no manual export; the secret is read at
       use time, never logged or cached to disk).
    """

    def __init__(self, dsn: str | None = None, env_file: Path | None = None):
        if not HAS_PSYCOPG2:
            raise DependencyMissingError(
                "psycopg2 not installed. Install with: pip install psycopg2-binary"
            )
        if env_file is not None:
            self._load_env_file(env_file)
        self.dsn = dsn or self._resolve_dsn()
        self._conn: Any = None

    @staticmethod
    def _load_env_file(env_file: Path) -> None:
        """Load KEY=VALUE pairs into os.environ from .env file."""
        if not env_file.exists():
            return
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

    @staticmethod
    def _dsn_from_systemd() -> str | None:
        """Read Environment=DATABASE_URL from the lia-backend systemd unit.

        Returns the URL or None when systemctl is unavailable / no match.
        The value is returned to the caller only -- never logged.
        """
        try:
            out = subprocess.run(
                ["systemctl", "cat", "lia-backend"],
                capture_output=True, text=True, timeout=5, check=False,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Environment=DATABASE_URL="):
                val = line[len("Environment=DATABASE_URL="):].strip().strip('"').strip("'")
                if val.startswith("postgresql"):
                    return val
        return None

    def _resolve_dsn(self) -> str:
        env = os.environ
        if "DATABASE_URL" in env:
            return env["DATABASE_URL"]
        # LIA_DB_* preferred
        host = env.get("LIA_DB_HOST") or env.get("PGHOST", "localhost")
        port = env.get("LIA_DB_PORT") or env.get("PGPORT", "5432")
        db = env.get("LIA_DB_NAME") or env.get("PGDATABASE", "lia_scan")
        user = env.get("LIA_DB_USER") or env.get("PGUSER", "lia_admin")
        pwd = env.get("LIA_DB_PASS") or env.get("PGPASSWORD", "")
        if not pwd:
            systemd_dsn = self._dsn_from_systemd()
            if systemd_dsn:
                return systemd_dsn
            raise DependencyMissingError(
                "PG password not found in env (set LIA_DB_PASS, PGPASSWORD, or "
                "DATABASE_URL); systemd lia-backend fallback also unavailable"
            )
        # Build DSN -- urlencode-safe for password
        from urllib.parse import quote
        return f"postgresql://{user}:{quote(pwd, safe='')}@{host}:{port}/{db}?sslmode=disable"

    def __enter__(self) -> PGClient:
        try:
            self._conn = psycopg2.connect(self.dsn)
        except psycopg2.OperationalError as e:
            raise DependencyMissingError(f"PG connection failed: {e}") from e
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def query(self, sql: str, params: dict | tuple | list | None = None) -> list[dict]:
        """Execute SELECT, return list of dicts.

        Args:
            sql: SQL string with %(name)s or %s placeholders
            params: dict for named placeholders, tuple/list for positional

        Raises:
            DependencyMissingError: query timeout or connection lost
        """
        if self._conn is None:
            raise EnrichError("PGClient not opened (use 'with' context)")
        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return [dict(r) for r in rows]
        except psycopg2.Error as e:
            raise DependencyMissingError(f"PG query failed: {e}") from e


# ======================================================================
# Canonical vendor resolver (LiaProbe <-> threat-intel sync)
# ======================================================================

# Minimum pg_trgm similarity to accept fuzzy match. Below this, return None so
# downstream cycles can proceed without a (potentially wrong) canonical id.
VENDOR_FUZZY_THRESHOLD = 0.55


class CanonicalVendorResolver:
    """Resolve a raw CPE vendor token to a canonical vendor_id via vendor_alias.

    Resolution chain:
    1. Exact case-insensitive match on `vendor_alias.alias_name`.
    2. pg_trgm similarity fallback (idx_vendor_alias_trgm GIN index), keeping
       results above VENDOR_FUZZY_THRESHOLD.
    3. None when no candidate above threshold (caller decides what to do).

    Output dict shape (matches the /api/admin/vendor-alias/resolve contract):
        {
            "vendor_id": int,
            "vendor_name": str,
            "alias_name": str,           # actual alias row that matched
            "alias_source": str,         # nvd_cpe / mitre_stix / cisa_kev / ...
            "alias_type": str | None,
            "confidence_score": float,   # 0..1 from vendor_alias row
            "resolved_via": "exact" | "fuzzy_trgm",
            "resolved_at": str,          # ISO 8601 UTC
            "similarity": float | None,  # populated when fuzzy_trgm
        }
    """

    def __init__(self, pg: PGClient):
        if pg is None:
            raise InvalidInputError("CanonicalVendorResolver requires an open PGClient")
        self._pg = pg

    @staticmethod
    def _normalize_token(token: str) -> str:
        """Strip cpe escaping, underscores -> spaces (heuristic)."""
        if token is None:
            return ""
        t = token.strip().lower()
        # cpe encodes spaces as `_`. Remove escaping backslashes first.
        return t.replace("\\", "").replace("_", " ")

    def resolve(self, cpe_vendor: str) -> dict | None:
        """Resolve a single CPE vendor token. Returns None on no match."""
        token = self._normalize_token(cpe_vendor)
        if not token:
            return None

        # Phase 1: exact (case-insensitive)
        rows = self._pg.query(
            """
            SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                   va.alias_type, va.confidence_score, v.vendor_name
            FROM vendor_alias va
            JOIN vendor v USING (vendor_id)
            WHERE lower(va.alias_name) = lower(%s)
            ORDER BY va.confidence_score DESC, va.id ASC
            LIMIT 1
            """,
            (token,),
        )
        if rows:
            r = rows[0]
            return {
                "vendor_id": int(r["vendor_id"]),
                "vendor_name": r["vendor_name"],
                "alias_name": r["alias_name"],
                "alias_source": r["alias_source"],
                "alias_type": r["alias_type"],
                "confidence_score": float(r["confidence_score"] or 0.0),
                "resolved_via": "exact",
                "resolved_at": utc_now_iso(),
                "similarity": None,
            }

        # Phase 2: pg_trgm fuzzy. similarity() requires pg_trgm extension.
        rows = self._pg.query(
            """
            SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                   va.alias_type, va.confidence_score, v.vendor_name,
                   similarity(va.alias_name, %s) AS sim
            FROM vendor_alias va
            JOIN vendor v USING (vendor_id)
            WHERE va.alias_name %% %s
            ORDER BY sim DESC, va.confidence_score DESC
            LIMIT 1
            """,
            (token, token),
        )
        if not rows:
            return None
        r = rows[0]
        sim = float(r["sim"] or 0.0)
        if sim < VENDOR_FUZZY_THRESHOLD:
            return None
        return {
            "vendor_id": int(r["vendor_id"]),
            "vendor_name": r["vendor_name"],
            "alias_name": r["alias_name"],
            "alias_source": r["alias_source"],
            "alias_type": r["alias_type"],
            "confidence_score": float(r["confidence_score"] or 0.0),
            "resolved_via": "fuzzy_trgm",
            "resolved_at": utc_now_iso(),
            "similarity": sim,
        }

    def resolve_full(self, vendor_token: str, product_token: str = "") -> dict | None:
        """Personalized resolution: vendor_id + product_id + alias_chain + sub_product flag.

        Returns dict carrying canonical LIA-SEC IDs for both vendor and product, plus
        the alias chain that bridged the resolution. Used to make each LiaProbe rule
        unique vs upstream tools (Wappalyzer/Recog/Nuclei) by binding it to the
        threat-intel vendor.product table identifiers.

        Resolution chain:
          A) vendor_alias exact match -> vendor_id
             Then product table match for product_token under that vendor_id.
             sub_product = True when product_token != alias_name (i.e. LiaProbe
             targets a sub-product of the canonical vendor).
          B) product table direct match on vendor_token (LiaProbe vendor token
             actually names a product whose canonical vendor is in the NVD
             product table). sub_product implicit.
          C) product_name ILIKE %vendor_token% with single dominant vendor (>=70%
             of hits). Lower confidence (0.65).
          D) None.

        Returns dict with keys:
          method, vendor_id, vendor_name, product_id, product_name_db,
          sub_product, alias_chain, confidence, ambiguous (when applicable),
          lia_signature_key (composite: lia_v<vendor_id>[_p<product_id>]),
          resolved_at.
        """
        token = self._normalize_token(vendor_token)
        if not token:
            return None
        product_token_n = (product_token or "").strip()

        # A) vendor_alias exact
        rows = self._pg.query(
            """
            SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                   va.alias_type, va.confidence_score, v.vendor_name
            FROM vendor_alias va
            JOIN vendor v USING (vendor_id)
            WHERE lower(va.alias_name) = lower(%s)
            ORDER BY va.confidence_score DESC, va.id ASC
            LIMIT 1
            """,
            (token,),
        )
        if rows:
            va = rows[0]
            product_id = None
            product_name_db = None
            sub_product = False
            if product_token_n:
                # Try exact product
                prows = self._pg.query(
                    """
                    SELECT product_id, product_name FROM product
                    WHERE vendor_id = %s AND lower(product_name) = lower(%s)
                    LIMIT 1
                    """,
                    (va["vendor_id"], product_token_n),
                )
                if not prows:
                    # ILIKE fallback within the same vendor scope
                    prows = self._pg.query(
                        """
                        SELECT product_id, product_name FROM product
                        WHERE vendor_id = %s AND product_name ILIKE %s
                        LIMIT 1
                        """,
                        (va["vendor_id"], f"%{product_token_n}%"),
                    )
                if prows:
                    p = prows[0]
                    product_id = int(p["product_id"])
                    product_name_db = p["product_name"]
                    sub_product = (
                        product_token_n.lower() != p["product_name"].lower()
                        and product_token_n.lower() != va["alias_name"].lower()
                    )
            return self._build_full_payload(
                method="alias_exact",
                vendor_id=int(va["vendor_id"]),
                vendor_name=va["vendor_name"],
                product_id=product_id,
                product_name_db=product_name_db,
                sub_product=sub_product,
                alias_chain=[{
                    "alias_name": va["alias_name"],
                    "alias_source": va["alias_source"],
                    "alias_type": va["alias_type"],
                    "confidence_score": float(va["confidence_score"] or 0.0),
                }],
                confidence=0.95,
            )

        # B) product table direct match on vendor_token (sub-product of NVD vendor)
        rows = self._pg.query(
            """
            SELECT v.vendor_id, v.vendor_name, p.product_id, p.product_name,
                   count(*) OVER (PARTITION BY v.vendor_id) AS hits
            FROM product p
            JOIN vendor v USING (vendor_id)
            WHERE lower(p.product_name) = lower(%s)
            ORDER BY hits DESC
            LIMIT 5
            """,
            (token,),
        )
        if rows:
            top = rows[0]
            ambiguous = len({r["vendor_id"] for r in rows}) > 1
            return self._build_full_payload(
                method="product_exact",
                vendor_id=int(top["vendor_id"]),
                vendor_name=top["vendor_name"],
                product_id=int(top["product_id"]),
                product_name_db=top["product_name"],
                sub_product=True,
                alias_chain=[],
                confidence=0.50 if ambiguous else 0.85,
                ambiguous=ambiguous,
            )

        # C) product_name ILIKE %vendor_token% with dominant vendor (>=70%)
        rows = self._pg.query(
            """
            SELECT v.vendor_id, v.vendor_name, p.product_id, p.product_name,
                   count(*) OVER (PARTITION BY v.vendor_id) AS hits
            FROM product p
            JOIN vendor v USING (vendor_id)
            WHERE p.product_name ILIKE %s
            ORDER BY hits DESC
            LIMIT 10
            """,
            (f"%{token}%",),
        )
        if rows:
            from collections import Counter
            vc = Counter(int(r["vendor_id"]) for r in rows)
            top_vid, top_count = vc.most_common(1)[0]
            total = sum(vc.values())
            if total > 0 and top_count / total >= 0.7:
                top = next(r for r in rows if int(r["vendor_id"]) == top_vid)
                return self._build_full_payload(
                    method="product_ilike_dominant",
                    vendor_id=top_vid,
                    vendor_name=top["vendor_name"],
                    product_id=int(top["product_id"]),
                    product_name_db=top["product_name"],
                    sub_product=True,
                    alias_chain=[],
                    confidence=0.65,
                )
        return None

    def resolve_via_product_only(self, product_token: str,
                                 similarity_threshold: float = 0.7) -> dict | None:
        """Resolve vendor via product name when no CPE vendor is available.

        Used as Phase B fallback when extract_cpe_vendor() returns None but
        the rule carries a usable rule.product. Returns lower confidence
        because the CPE vendor (authoritative source) is missing -- callers
        MUST flag the resulting attribution as DOUBTFUL by default.

        Resolution chain:
          P1) product table exact match on product_name with single dominant
              vendor (>=70% of hits). confidence=0.55.
          P2) product_name ILIKE %product_token% with dominant vendor.
              confidence=0.45.
          P3) None.
        """
        token = (product_token or "").strip()
        if not token:
            return None

        # P1: exact product_name match
        rows = self._pg.query(
            """
            SELECT v.vendor_id, v.vendor_name, p.product_id, p.product_name,
                   count(*) OVER (PARTITION BY v.vendor_id) AS hits
            FROM product p
            JOIN vendor v USING (vendor_id)
            WHERE lower(p.product_name) = lower(%s)
            ORDER BY hits DESC
            LIMIT 5
            """,
            (token,),
        )
        if rows:
            from collections import Counter
            vc = Counter(int(r["vendor_id"]) for r in rows)
            top_vid, top_count = vc.most_common(1)[0]
            total = sum(vc.values())
            if total > 0 and top_count / total >= similarity_threshold:
                top = next(r for r in rows if int(r["vendor_id"]) == top_vid)
                ambiguous = len(vc) > 1
                return self._build_full_payload(
                    method="product_only_exact",
                    vendor_id=top_vid,
                    vendor_name=top["vendor_name"],
                    product_id=int(top["product_id"]),
                    product_name_db=top["product_name"],
                    sub_product=False,
                    alias_chain=[],
                    confidence=0.55,
                    ambiguous=ambiguous,
                )

        # P2: ILIKE fallback
        rows = self._pg.query(
            """
            SELECT v.vendor_id, v.vendor_name, p.product_id, p.product_name,
                   count(*) OVER (PARTITION BY v.vendor_id) AS hits
            FROM product p
            JOIN vendor v USING (vendor_id)
            WHERE p.product_name ILIKE %s
            ORDER BY hits DESC
            LIMIT 10
            """,
            (f"%{token}%",),
        )
        if rows:
            from collections import Counter
            vc = Counter(int(r["vendor_id"]) for r in rows)
            top_vid, top_count = vc.most_common(1)[0]
            total = sum(vc.values())
            if total > 0 and top_count / total >= similarity_threshold:
                top = next(r for r in rows if int(r["vendor_id"]) == top_vid)
                ambiguous = len(vc) > 1
                return self._build_full_payload(
                    method="product_only_ilike",
                    vendor_id=top_vid,
                    vendor_name=top["vendor_name"],
                    product_id=int(top["product_id"]),
                    product_name_db=top["product_name"],
                    sub_product=False,
                    alias_chain=[],
                    confidence=0.45,
                    ambiguous=ambiguous,
                )
        return None

    def resolve_via_taxonomy_first_token(self, taxonomy_code: str) -> dict | None:
        """Phase C1 strategy 5: resolve vendor from taxonomy_code first token.

        Splits taxonomy on '_', takes parts[0] as candidate vendor.
        ONLY accepts alias_exact match. Filters TAXONOMY_NOISE_FIRST_TOKENS
        denylist (THE/EASY/ABLE/GRAPHQL/GENERIC/UNKNOWN/MISC/...) confirmed
        false-positives in brainstorm_phase_c (2026-05-04).

        Returns DOUBTFUL-flagged payload (method=`taxonomy_first_token`,
        confidence=0.50) or None.
        """
        tc = (taxonomy_code or "").strip()
        if not tc:
            return None
        parts = tc.split("_")
        if not parts:
            return None
        first = parts[0].strip()
        if not first or len(first) < 2 or first.isdigit():
            return None
        if is_taxonomy_noise(first):
            return None
        # alias_exact only -- no fuzzy_trgm fallback per adversarial guard
        rows = self._pg.query(
            """
            SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                   va.alias_type, va.confidence_score, v.vendor_name
            FROM vendor_alias va
            JOIN vendor v USING (vendor_id)
            WHERE lower(va.alias_name) = lower(%s)
            ORDER BY va.confidence_score DESC, va.id ASC
            LIMIT 1
            """,
            (first,),
        )
        if not rows:
            return None
        va = rows[0]
        return self._build_full_payload(
            method="taxonomy_first_token",
            vendor_id=int(va["vendor_id"]),
            vendor_name=va["vendor_name"],
            product_id=None,
            product_name_db=None,
            sub_product=False,
            alias_chain=[{
                "alias_name": va["alias_name"],
                "alias_source": va["alias_source"],
                "alias_type": va["alias_type"],
                "confidence_score": float(va["confidence_score"] or 0.0),
            }],
            confidence=0.50,
        )

    def resolve_via_filename_token(self, filename: str) -> dict | None:
        """Phase C1 strategy 2: resolve vendor from JSON filename.

        Drops .json extension, takes first underscore-split token, lowercases.
        Skips LIA_ prefix (internal naming) and protocol/runtime noise.
        ONLY accepts alias_exact match. Killed B/C ILIKE paths per agent 2
        report (FP rate too high without strict guard).

        Returns DOUBTFUL-flagged payload (method=`filename_token`,
        confidence=0.50) or None.
        """
        f = (filename or "").strip()
        if not f:
            return None
        if f.lower().endswith(".json"):
            f = f[:-5]
        # LIA_ prefix means internal protocol naming, never a vendor token
        if f.upper().startswith("LIA_") or f.upper().startswith("LIA-"):
            return None
        # Take first underscore-split token
        parts = f.replace("-", "_").split("_")
        if not parts:
            return None
        first = parts[0].strip().lower()
        if not first or len(first) < 3 or first.isdigit():
            return None
        if is_protocol_noise(first) or is_runtime_noise(first):
            return None
        # alias_exact only
        rows = self._pg.query(
            """
            SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                   va.alias_type, va.confidence_score, v.vendor_name
            FROM vendor_alias va
            JOIN vendor v USING (vendor_id)
            WHERE lower(va.alias_name) = lower(%s)
            ORDER BY va.confidence_score DESC, va.id ASC
            LIMIT 1
            """,
            (first,),
        )
        if not rows:
            return None
        va = rows[0]
        return self._build_full_payload(
            method="filename_token",
            vendor_id=int(va["vendor_id"]),
            vendor_name=va["vendor_name"],
            product_id=None,
            product_name_db=None,
            sub_product=False,
            alias_chain=[{
                "alias_name": va["alias_name"],
                "alias_source": va["alias_source"],
                "alias_type": va["alias_type"],
                "confidence_score": float(va["confidence_score"] or 0.0),
            }],
            confidence=0.50,
        )

    def resolve_via_id_slug(self, rule_id: str, subdir: str = "") -> dict | None:
        """Phase C2 strategy 1: parse rule.id slug for vendor token.

        Expects format `proto-vendor-product[-...]` (tcp-probes only -- other
        subdirs use different naming, scope-restricted per agent 1 + agent 6
        analysis). Strips first token if it matches a known protocol prefix
        in PROTOCOL_NOISE_TOKENS. Then attempts alias_exact on second token.

        Restricted to subdir == "tcp-probes" by guard agent_1 + agent_6
        consensus (banner-signatures, web-signatures, lia, service-detectors
        do not use this naming).

        Returns DOUBTFUL-flagged payload (method=`id_slug_token`,
        confidence=0.55) or None.
        """
        if subdir and "tcp-probes" not in subdir:
            return None
        rid = (rule_id or "").strip().lower()
        if not rid:
            return None
        parts = rid.replace("_", "-").split("-")
        if len(parts) < 2:
            return None
        # Strip protocol prefix if first token is a known protocol/category
        first = parts[0]
        if not is_protocol_noise(first):
            # If first token is not a protocol, this is not the
            # `proto-vendor-product` pattern -- abstain.
            return None
        # Second token is the vendor candidate
        vendor_candidate = parts[1].strip()
        if not vendor_candidate or len(vendor_candidate) < 3:
            return None
        if is_protocol_noise(vendor_candidate) or is_runtime_noise(vendor_candidate):
            return None
        # alias_exact only
        rows = self._pg.query(
            """
            SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                   va.alias_type, va.confidence_score, v.vendor_name
            FROM vendor_alias va
            JOIN vendor v USING (vendor_id)
            WHERE lower(va.alias_name) = lower(%s)
            ORDER BY va.confidence_score DESC, va.id ASC
            LIMIT 1
            """,
            (vendor_candidate,),
        )
        if not rows:
            return None
        va = rows[0]
        return self._build_full_payload(
            method="id_slug_token",
            vendor_id=int(va["vendor_id"]),
            vendor_name=va["vendor_name"],
            product_id=None,
            product_name_db=None,
            sub_product=False,
            alias_chain=[{
                "alias_name": va["alias_name"],
                "alias_source": va["alias_source"],
                "alias_type": va["alias_type"],
                "confidence_score": float(va["confidence_score"] or 0.0),
            }],
            confidence=0.55,
        )

    def resolve_via_website_domain(self, website_url: str) -> dict | None:
        """Phase E strategy 1: resolve vendor from rule.website root domain.

        Uses extract_root_domain() to parse URL -> SLD with comprehensive
        denylist (CODE_HOSTS, BLOG_HOSTS, CDN_HOSTS, SAAS_MARKETPLACES,
        DOC_HOSTS) and multi-level TLD handling.

        Brainstorm Phase D (2026-05-04) findings:
        - 3,592 SKIP rules have website field
        - Raw resolution: 189 hits = 5.3% yield
        - Post-denylist: 152 clean TPs = 4.2% yield
        - FP rate post-guard: 8% residual

        Returns DOUBTFUL-flagged payload (method=`website_domain`,
        confidence=0.50) or None.
        """
        root = extract_root_domain(website_url)
        if not root:
            return None
        # alias_exact only -- no fuzzy_trgm
        rows = self._pg.query(
            """
            SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                   va.alias_type, va.confidence_score, v.vendor_name
            FROM vendor_alias va
            JOIN vendor v USING (vendor_id)
            WHERE lower(va.alias_name) = lower(%s)
            ORDER BY va.confidence_score DESC, va.id ASC
            LIMIT 1
            """,
            (root,),
        )
        if not rows:
            return None
        va = rows[0]
        return self._build_full_payload(
            method="website_domain",
            vendor_id=int(va["vendor_id"]),
            vendor_name=va["vendor_name"],
            product_id=None,
            product_name_db=None,
            sub_product=False,
            alias_chain=[{
                "alias_name": va["alias_name"],
                "alias_source": va["alias_source"],
                "alias_type": va["alias_type"],
                "confidence_score": float(va["confidence_score"] or 0.0),
            }],
            confidence=0.50,
        )

    def resolve_via_taxonomy_name_capword(self, taxonomy_name: str) -> dict | None:
        """Phase D strategy 2: resolve vendor from taxonomy_name first capword.

        Splits taxonomy_name on whitespace, takes first token lowercased.
        Skips if first token is in PROTOCOL_NOISE_TOKENS, RUNTIME_NOISE_VENDORS,
        or TAXONOMY_NOISE_FIRST_TOKENS denylists. Tries alias_exact match.

        Solo analysis 2026-05-04 (rate-limit blocked agent brainstorm):
        7,600 attempts -> 650 hits (8.6% yield), 20-sample 100% TP rate
        with extended denylist (Coin/Cookie/Daily/Smart/Simple/Modern...).

        Returns DOUBTFUL-flagged payload (method=`taxonomy_name_capword`,
        confidence=0.50) or None.
        """
        tn = (taxonomy_name or "").strip()
        if not tn:
            return None
        parts = tn.split()
        if not parts:
            return None
        first = parts[0].strip().lower()
        if not first or len(first) < 3:
            return None
        if (is_protocol_noise(first) or is_runtime_noise(first)
                or is_taxonomy_noise(first)):
            return None
        # alias_exact only -- no fuzzy_trgm
        rows = self._pg.query(
            """
            SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                   va.alias_type, va.confidence_score, v.vendor_name
            FROM vendor_alias va
            JOIN vendor v USING (vendor_id)
            WHERE lower(va.alias_name) = lower(%s)
            ORDER BY va.confidence_score DESC, va.id ASC
            LIMIT 1
            """,
            (first,),
        )
        if not rows:
            return None
        va = rows[0]
        return self._build_full_payload(
            method="taxonomy_name_capword",
            vendor_id=int(va["vendor_id"]),
            vendor_name=va["vendor_name"],
            product_id=None,
            product_name_db=None,
            sub_product=False,
            alias_chain=[{
                "alias_name": va["alias_name"],
                "alias_source": va["alias_source"],
                "alias_type": va["alias_type"],
                "confidence_score": float(va["confidence_score"] or 0.0),
            }],
            confidence=0.50,
        )

    def resolve_via_notes_capword(self, notes: str, tags: list | None = None) -> dict | None:
        """Phase C2 strategy 4: tag-token-only resolution.

        v9 sample verify (2026-05-04) showed 60% FP rate when mining
        capitalized words from notes -- notes frequently follow the pattern
        "X is an Y app" where Y is the platform (Shopify, WordPress, Whatsapp)
        not the actual vendor X. Examples of confirmed FPs:
          - BITESPEED.json -> Shopify (real vendor: Bitespeed)
          - PUSHDADDY_WHATSAPP_CHAT.json -> Whatsapp (real vendor: Pushdaddy)
          - PANDECTES.json -> Shopify (real vendor: Pandectes)
          - PYTHONANYWHERE.json -> Platform (generic noun)

        Resolution restricted to `tags[]` array: per agent 4 report,
        53.4% of service-detectors tags resolve cleanly. Tags are direct
        author labels, not free-text contamination.

        Returns DOUBTFUL-flagged payload (method=`notes_capword`,
        confidence=0.50) or None.
        """
        # NOTE: `notes` argument is preserved for API stability but no longer
        # mined -- v9 sample confirmed 60% FP rate from notes capword extraction.
        _ = notes  # intentionally unused
        candidates: list[str] = []

        # Tag tokens only -- agent 4 verified 53% clean resolution rate
        if tags and isinstance(tags, list):
            for t in tags:
                if isinstance(t, str):
                    tl = t.strip().lower()
                    if tl and len(tl) >= 3:
                        if not is_runtime_noise(tl) and not is_protocol_noise(tl):
                            candidates.append(tl)

        if not candidates:
            return None

        # Dedup preserving order
        seen = set()
        ordered = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                ordered.append(c)

        # Try alias_exact on each candidate, return first hit
        for cand in ordered:
            rows = self._pg.query(
                """
                SELECT va.vendor_id, va.alias_name, va.source AS alias_source,
                       va.alias_type, va.confidence_score, v.vendor_name
                FROM vendor_alias va
                JOIN vendor v USING (vendor_id)
                WHERE lower(va.alias_name) = lower(%s)
                ORDER BY va.confidence_score DESC, va.id ASC
                LIMIT 1
                """,
                (cand,),
            )
            if rows:
                va = rows[0]
                return self._build_full_payload(
                    method="notes_capword",
                    vendor_id=int(va["vendor_id"]),
                    vendor_name=va["vendor_name"],
                    product_id=None,
                    product_name_db=None,
                    sub_product=False,
                    alias_chain=[{
                        "alias_name": va["alias_name"],
                        "alias_source": va["alias_source"],
                        "alias_type": va["alias_type"],
                        "confidence_score": float(va["confidence_score"] or 0.0),
                    }],
                    confidence=0.50,
                )
        return None

    @staticmethod
    def _build_full_payload(*, method, vendor_id, vendor_name, product_id,
                            product_name_db, sub_product, alias_chain, confidence,
                            ambiguous=False):
        lia_key = f"lia_v{vendor_id}"
        if product_id is not None:
            lia_key += f"_p{product_id}"
        return {
            "method": method,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "product_id": product_id,
            "product_name_db": product_name_db,
            "sub_product": sub_product,
            "alias_chain": alias_chain,
            "confidence": confidence,
            "ambiguous": ambiguous,
            "lia_signature_key": lia_key,
            "resolved_at": utc_now_iso(),
        }


# ======================================================================
# Phase C false-positive denylists -- block known wrong attributions.
# Source: brainstorm_phase_c/CONSOLIDATED.md (2026-05-04, 6 agents).
# Each entry blocked must trace to a concrete file path in
# false_positive_corpus.md or in the 6 agent reports.
# ======================================================================

# Runtime-vs-vendor trap: these strings appear in rule.notes for many real
# vendors who use these as runtime/server underneath their product. Notes
# mining MUST NOT extract them as canonical vendor attribution.
# Examples documented:
#   - CHKMK.json (vendor=tribe29) notes "Serveur Apache sous-jacent"
#   - BAMBO.json (vendor=Atlassian) notes "Uses Tomcat"
RUNTIME_NOISE_VENDORS: frozenset[str] = frozenset({
    "apache", "tomcat", "nginx", "openssh", "openssl",
    "java", "python", "ruby", "perl", "node", "nodejs",
    "iis", "lighttpd", "linux", "windows", "unix",
})

# Generic protocol/concept tokens that frequently appear in id slugs and
# filenames but identify a service category, not a vendor. Phase C id slug
# parser + filename parser MUST blacklist these.
PROTOCOL_NOISE_TOKENS: frozenset[str] = frozenset({
    "proxy", "upnp", "rtsp", "finger", "ident", "ssl", "tls",
    "wp", "login", "web", "dns", "ftp", "tcp", "http", "https",
    "smtp", "imap", "pop3", "ssh", "telnet", "snmp", "sip",
    "irc", "rdp", "vnc", "x11", "nntp", "rtp", "ldap", "kerberos",
    "auth", "admin", "console", "service", "server", "client",
    "module", "protocol", "session", "default", "test", "demo",
    "generic", "unknown", "misc", "other", "various",
    # Added 2026-05-04 v10 sample verify (TFTP and NTP slipped through
    # as canonical "vendor" via vendor_alias entries that are actually
    # protocol identifiers, not real vendors)
    "tftp", "ntp", "sftp", "syslog", "dhcp", "udp", "icmp",
    "smb", "cifs", "nfs", "rpc", "rmi", "soap", "rest", "graphql",
    "tcpip", "ipv4", "ipv6", "ipsec", "vpn", "scada", "modbus",
})

# Taxonomy-code first-tokens proven to misresolve via vendor_alias even
# when an alias_exact match exists -- because the alias entry is
# meaningless or unrelated (e.g. THE.json -> "The-Sz" alias).
TAXONOMY_NOISE_FIRST_TOKENS: frozenset[str] = frozenset({
    "THE", "EASY", "ABLE", "GRAPHQL", "GENERIC", "UNKNOWN",
    "MISC", "OTHER", "VARIOUS", "DEFAULT", "DEMO", "TEST",
    # Added 2026-05-04 from v8 sample verify (FILE_MANAGER -> File,
    # COMMERCE_JS -> Commerce -- too generic, real vendor is the full
    # product name, not just first token).
    "FILE", "COMMERCE", "WEB", "MOBILE", "API", "DETECT",
    "MANAGER", "SERVER", "CLIENT", "PLATFORM", "CMS",
    # Added 2026-05-04 Phase D taxonomy_name first-capword analysis
    # (FP candidates: Coin, Cookie, Daily, Smart, Simple, Modern, ...).
    "COIN", "COOKIE", "DAILY", "WEEKLY", "MONTHLY", "TOP",
    "BEST", "NEW", "CUSTOM", "PRO", "PLUS", "MINI", "BASIC",
    "ULTRA", "PREMIUM", "STANDARD", "EXTENDED", "LIGHT",
    "SMART", "SIMPLE", "MODERN", "QUICK", "FAST", "SLOW",
    "ACTIVE", "PASSIVE", "INACTIVE",
    # Added 2026-05-04 Phase D agent_2 retroactive validation reco
    # (preventive: NVD seed expansion may add cpe_dict vendors with
    # these short generic names creating future FP).
    "OPEN", "DIGITAL", "GLOBAL", "NETWORK", "SECURE",
})

# Website domain extraction denylists (Phase E, agent 5 + 6 brainstorm).
# When the website root domain matches these, the URL points to the
# hosting/distribution platform, NOT the actual vendor.
WEBSITE_CODE_HOSTS: frozenset[str] = frozenset({
    "github", "gitlab", "bitbucket", "sourceforge",
    "gitea", "codeberg", "framagit", "savannah",
})
WEBSITE_BLOG_HOSTS: frozenset[str] = frozenset({
    "wordpress", "blogspot", "medium", "tumblr",
    "weebly", "wix", "squarespace", "substack",
    "ghost",
})
WEBSITE_CDN_HOSTS: frozenset[str] = frozenset({
    "cloudflare", "akamai", "fastly", "cloudfront",
    "jsdelivr", "unpkg", "azureedge",
})
WEBSITE_SAAS_MARKETPLACES: frozenset[str] = frozenset({
    "shopify", "atlassian", "apple", "amazon",
    "amazonaws", "google", "microsoft", "salesforce",
    "hubspot",
})
WEBSITE_DOC_HOSTS: frozenset[str] = frozenset({
    "readthedocs", "gitbook", "docusaurus", "mkdocs",
    "rfc", "ietf", "w3", "iana",
})
WEBSITE_NOISE_HOSTS: frozenset[str] = (
    WEBSITE_CODE_HOSTS
    | WEBSITE_BLOG_HOSTS
    | WEBSITE_CDN_HOSTS
    | WEBSITE_SAAS_MARKETPLACES
    | WEBSITE_DOC_HOSTS
)

# Multi-level public TLD list (manual curation; tldextract not available).
# Used to extract second-level domain (SLD) from URLs like foo.co.uk
# correctly as "foo" not "co".
WEBSITE_MULTI_TLD: frozenset[str] = frozenset({
    "co.uk", "co.jp", "co.kr", "co.za", "co.nz", "co.id", "co.in",
    "com.au", "com.br", "com.mx", "com.cn", "com.tw", "com.hk",
    "com.sg", "com.tr", "com.ar", "com.co", "com.pk", "com.eg",
    "com.ph", "com.my", "com.pe", "com.ve", "com.uy", "com.do",
    "com.ec", "com.bo", "com.py", "com.gt", "com.cr", "com.ng",
    "com.gh", "com.lb", "com.sa",
    "gov.uk", "gov.au", "gov.in",
    "ac.uk", "ac.jp", "ac.in", "ac.nz", "ac.za",
    "org.uk", "org.au", "or.jp", "or.kr",
    "ne.jp", "go.jp", "ed.jp", "lg.jp",
    "edu.au", "edu.cn",
})


def is_runtime_noise(token: str) -> bool:
    """True if token is a runtime/library name commonly mentioned in notes
    of products that do NOT belong to that runtime's vendor.
    """
    return (token or "").strip().lower() in RUNTIME_NOISE_VENDORS


def extract_root_domain(url: str) -> str | None:
    """Extract second-level domain (vendor identifier) from a website URL.

    Handles:
      - http/https/ftp scheme
      - Subdomain prefixes (www., m., api., admin., app., apps., cdn.,
        static., store., marketplace., addons., docs., blog., support.)
      - Multi-level TLDs (co.uk, com.au, gov.uk, ac.jp, etc)
      - Punycode (xn--...) via idna decode (graceful fallback)
      - Returns None for noise hosts (code/blog/CDN/SaaS/doc)
      - Returns None for IP-based URLs

    Phase E (agent 5 + 6 brainstorm): production parser feeding website
    domain resolver. Tested 21/21 unit cases + 15 real LiaProbe URLs.
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None

    from urllib.parse import urlparse
    # Auto-prefix scheme if missing
    if "://" not in url:
        url = "http://" + url
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().lstrip(".")
    except Exception:
        return None
    if not host:
        return None

    # Reject IP-based URLs
    import re as _re
    if _re.fullmatch(r"[\d.:]+", host):
        return None

    # Decode punycode if present
    if "xn--" in host:
        try:
            import idna
            host = idna.decode(host)
        except Exception:
            return None

    # Strip common subdomain prefixes (one level only)
    SUBDOMAIN_PREFIXES = (
        "www.", "m.", "api.", "admin.", "app.", "apps.",
        "cdn.", "static.", "store.", "marketplace.", "addons.",
        "docs.", "blog.", "support.", "help.", "wiki.",
    )
    for prefix in SUBDOMAIN_PREFIXES:
        if host.startswith(prefix):
            host = host[len(prefix):]
            break  # only strip one prefix level

    parts = host.split(".")
    if len(parts) < 2:
        return None

    # Multi-level TLD: if last 2 parts form a known multi-tld,
    # take parts[-3] as SLD; otherwise parts[-2].
    if len(parts) >= 3:
        last_two = ".".join(parts[-2:])
        if last_two in WEBSITE_MULTI_TLD:
            sld = parts[-3]
        else:
            sld = parts[-2]
    else:
        sld = parts[-2]

    if not sld or len(sld) < 3:
        return None
    if sld.isdigit():
        return None
    if sld in WEBSITE_NOISE_HOSTS:
        return None
    return sld


def is_protocol_noise(token: str) -> bool:
    """True if token is a protocol/category label rather than a vendor."""
    return (token or "").strip().lower() in PROTOCOL_NOISE_TOKENS


def is_taxonomy_noise(token: str) -> bool:
    """True if token is a known noisy taxonomy first-token."""
    return (token or "").strip().upper() in TAXONOMY_NOISE_FIRST_TOKENS


def _parse_cpe(cpe: str) -> tuple[str | None, str | None, str | None]:
    """Parse a CPE 2.3 or CPE 2.2 string into (part, vendor, product).

    Supports:
      - CPE 2.3 (`cpe:2.3:<part>:<vendor>:<product>:...`)
      - CPE 2.2 (`cpe:/<part>:<vendor>:<product>[:version]`)
    Returns (None, None, None) on parse failure or wildcard fields.
    """
    if not cpe or not isinstance(cpe, str):
        return None, None, None
    cpe = cpe.strip()
    parts: list[str]
    part_idx = vendor_idx = product_idx = None
    if cpe.startswith("cpe:2.3:"):
        parts = cpe.split(":")
        if len(parts) < 5:
            return None, None, None
        part_idx, vendor_idx, product_idx = 2, 3, 4
    elif cpe.startswith("cpe:/"):
        # CPE 2.2: cpe:/<part>:<vendor>:<product>[:version[:update[:edition]]]
        body = cpe[len("cpe:/"):]
        parts = body.split(":")
        if not parts or not parts[0]:
            return None, None, None
        part_idx, vendor_idx, product_idx = 0, 1, 2
    else:
        return None, None, None

    def _at(i: int) -> str | None:
        if i < len(parts):
            v = parts[i].strip()
            if v and v != "*":
                return v
        return None

    return _at(part_idx), _at(vendor_idx), _at(product_idx)


def _cpe_part_is_application(cpe: str) -> bool:
    """Return True only when cpe23_template targets an application (`:a:`).

    Kept for backward compatibility with existing callers/tests. New code
    should prefer `_cpe_part_classify(cpe)` which also distinguishes `h` and
    `o`.
    """
    part, _, _ = _parse_cpe(cpe)
    return part == "a"


def _cpe_part_classify(cpe: str) -> str | None:
    """Return the CPE part letter ('a', 'h', 'o') or None if unparsed.

    `a` = application (service vendor, fully trusted).
    `h` = hardware (device vendor, trusted -- legitimate constructor of the
          appliance, e.g. cpe:2.3:h:bosch:ip_bullet_5000).
    `o` = operating system (NOT trusted as service vendor -- represents the
          OS host, not the detected service. Mass-misattribution risk).
    """
    part, _, _ = _parse_cpe(cpe)
    return part


def extract_cpe_product(rule: dict) -> str:
    """Extract a product token from a fingerprint rule for canonical resolution.

    Order:
      1. cpe23_template parts[4] when part is `:a:` or `:h:`
      2. rule.product
      3. rule.taxonomy_name
    `:o:` is intentionally rejected because it identifies the OS host, not the
    service product (mass-misattribution risk -- see incident 2026-05-03).
    Returns empty string when nothing usable.
    """
    cpe = rule.get("cpe23_template", "") or ""
    part, _, product = _parse_cpe(cpe)
    if part in ("a", "h") and product:
        return product
    p = (rule.get("product") or "").strip()
    if p:
        return p
    return (rule.get("taxonomy_name") or "").strip()


def extract_cpe_vendor(rule: dict) -> str | None:
    """Extract the CPE vendor token from a fingerprint rule.

    Trusts cpe parts[3] when target is an application (`:a:`) OR a hardware
    device (`:h:`). `:h:` vendors are legitimate device constructors (Bosch,
    Motorola, Conceptronic) and are accepted as canonical vendors of the
    appliance the rule fingerprints.

    `:o:` (OS host context) is REJECTED -- in tcp-probes on Windows hosts the
    cpe23 reads `cpe:2.3:o:microsoft:windows:*` for any service that runs on
    Windows, and trusting that field mass-misattributed 521 rules to Microsoft
    in v3 of this resolver. Fall back to rule.vendor / rule.product instead.
    """
    cpe = rule.get("cpe23_template", "") or ""
    part, vendor, _ = _parse_cpe(cpe)
    if part in ("a", "h") and vendor:
        return vendor
    fallback = (rule.get("vendor") or "").strip()
    return fallback or None


# ======================================================================
# Structured logger (append-only JSONL)
# ======================================================================

class StructuredLogger:
    """Append-only JSONL logger for audit trail.

    File grows monotonically. Concurrent writers safe via O_APPEND on POSIX.
    """

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, **fields: Any) -> None:
        """Append a JSON event to the log."""
        event = {"timestamp": utc_now_iso(), **fields}
        line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        # O_APPEND on POSIX is atomic for small writes (<4096 bytes)
        fd = os.open(str(self.log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)


# ======================================================================
# State manager
# ======================================================================

@dataclasses.dataclass
class CycleStatus:
    status: str = "pending"  # pending / in_progress / completed / failed / skipped
    applied_at: str | None = None
    applied_count: int = 0
    evidence_path: str | None = None
    evidence_sha256: str | None = None
    summary: dict = dataclasses.field(default_factory=dict)
    last_drift_check: str | None = None
    last_drift_status: str | None = None
    skip_reason: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in dataclasses.asdict(self).items() if v is not None and v != {}}

    @classmethod
    def from_dict(cls, d: dict) -> CycleStatus:
        return cls(
            status=d.get("status", "pending"),
            applied_at=d.get("applied_at"),
            applied_count=d.get("applied_count", 0),
            evidence_path=d.get("evidence_path"),
            evidence_sha256=d.get("evidence_sha256"),
            summary=d.get("summary", {}),
            last_drift_check=d.get("last_drift_check"),
            last_drift_status=d.get("last_drift_status"),
            skip_reason=d.get("skip_reason"),
        )


CYCLES = (
    "cycle_4_cve",
    "cycle_5_eol",
    "cycle_6_compliance",
    "cycle_7_mitre",
    "cycle_8_default_creds",
    "cycle_9_cert_patterns",
    "cycle_10_behavior",
    "cycle_11_cluster_tls",
    "cycle_12_honeypot",
)


class StateManager:
    """Per-rule state file manager.

    State file: <state_dir>/<sha1_path>.state.json
    Lock file:  <state_dir>/<sha1_path>.lock
    """

    SCHEMA_VERSION = "lia-enrich-state-v1"

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, rule_path: Path) -> Path:
        return self.state_dir / f"{sha1_path(rule_path)}.state.json"

    def _lock_path(self, rule_path: Path) -> Path:
        return self.state_dir / f"{sha1_path(rule_path)}.lock"

    def load(self, rule_path: Path) -> dict:
        """Load state file or return fresh state if missing."""
        path = self._state_path(rule_path)
        if not path.exists():
            return self._fresh_state(rule_path)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise EnrichError(f"State file unreadable: {path}: {e}") from e

    def save(self, rule_path: Path, state: dict) -> None:
        """Save state file atomically."""
        AtomicJSONWriter.write(self._state_path(rule_path), state)

    def lock(self, rule_path: Path, timeout_s: float | None = None) -> LockManager:
        """Return a LockManager bound to this rule (use as context)."""
        return LockManager(self._lock_path(rule_path), timeout_s=timeout_s)

    def _fresh_state(self, rule_path: Path) -> dict:
        return {
            "$schema": self.SCHEMA_VERSION,
            "rule": {
                "path": str(rule_path),
                "id": None,
                "taxonomy_code": None,
                "rule_sha256_initial": None,
                "rule_sha256_current": None,
            },
            "lifecycle_state": "PRISTINE",
            "lifecycle_history": [],
            "first_enriched_at": None,
            "last_enriched_at": None,
            "cycles": {c: CycleStatus().to_dict() for c in CYCLES},
            "transformative_score": {"before": None, "after_enrich": None, "history": []},
            "errors": [],
            "audit": {
                "first_seen": utc_now_iso(),
                "rule_modified_externally_count": 0,
                "drift_critical_count": 0,
                "tamper_detected_count": 0,
            },
        }

    def get_cycle_status(self, rule_path: Path, cycle_id: str) -> CycleStatus:
        if cycle_id not in CYCLES:
            raise InvalidInputError(f"Unknown cycle: {cycle_id}")
        state = self.load(rule_path)
        return CycleStatus.from_dict(state["cycles"].get(cycle_id, {}))

    def mark_cycle_done(
        self,
        rule_path: Path,
        cycle_id: str,
        evidence_path: Path,
        evidence_sha256: str,
        summary: dict,
    ) -> None:
        if cycle_id not in CYCLES:
            raise InvalidInputError(f"Unknown cycle: {cycle_id}")
        state = self.load(rule_path)
        cur = CycleStatus.from_dict(state["cycles"].get(cycle_id, {}))
        cur.status = "completed"
        cur.applied_at = utc_now_iso()
        cur.applied_count = (cur.applied_count or 0) + 1
        cur.evidence_path = str(evidence_path)
        cur.evidence_sha256 = evidence_sha256
        cur.summary = summary
        state["cycles"][cycle_id] = cur.to_dict()
        # Update lifecycle if first enrich
        if state["lifecycle_state"] == "PRISTINE":
            state["lifecycle_state"] = "ENRICHED"
            state["first_enriched_at"] = state["first_enriched_at"] or utc_now_iso()
            state["lifecycle_history"].append({
                "to": "ENRICHED",
                "at": utc_now_iso(),
                "trigger": "first_enrich",
            })
        state["last_enriched_at"] = utc_now_iso()
        self.save(rule_path, state)

    def mark_cycle_skipped(
        self, rule_path: Path, cycle_id: str, reason: str
    ) -> None:
        if cycle_id not in CYCLES:
            raise InvalidInputError(f"Unknown cycle: {cycle_id}")
        state = self.load(rule_path)
        cur = CycleStatus.from_dict(state["cycles"].get(cycle_id, {}))
        cur.status = "skipped"
        cur.skip_reason = reason
        cur.applied_at = utc_now_iso()
        state["cycles"][cycle_id] = cur.to_dict()
        self.save(rule_path, state)


# ======================================================================
# Evidence writer
# ======================================================================

class EvidenceWriter:
    """Write evidence files atomically with sha256 integrity.

    Path layout:
      <enrichment_dir>/<RULE_DIR>/evidence/cycle_<N>_<theme>_<ISO>.json
      <enrichment_dir>/<RULE_DIR>/evidence/cycle_<N>_<theme>_latest.symlink

    enrichment_dir = data/enrichment (parallel to data/fingerprints)
    RULE_DIR is derived from rule path (see compute_enrichment_dir).
    """

    SCHEMA_VERSION = "lia-enrich-evidence-v1"

    def __init__(self, enrichment_root: Path, fingerprints_root: Path, patterns_root: Path | None = None):
        self.enrichment_root = Path(enrichment_root)
        self.fingerprints_root = Path(fingerprints_root)
        self.patterns_root = Path(patterns_root) if patterns_root else None

    def compute_enrichment_dir(self, rule_path: Path) -> Path:
        """Map rule path to enrichment subdir.

        data/fingerprints/lia/JENKINS.json -> data/enrichment/lia/JENKINS/
        patterns/lia/JENKINS.json          -> data/enrichment/_patterns/lia/JENKINS/
        """
        rule_path = Path(rule_path).resolve()
        try:
            rel = rule_path.relative_to(self.fingerprints_root)
            base = self.enrichment_root
        except ValueError:
            if self.patterns_root and rule_path.is_relative_to(self.patterns_root):
                rel = rule_path.relative_to(self.patterns_root)
                base = self.enrichment_root / "_patterns"
            else:
                raise InvalidInputError(
                    f"Rule path {rule_path} not under fingerprints_root or patterns_root"
                )
        # Strip .json extension to get RULE dir name
        return base / rel.parent / rel.stem

    def evidence_path(self, rule_path: Path, cycle_id: str) -> Path:
        """Compute timestamped evidence file path."""
        d = self.compute_enrichment_dir(rule_path) / "evidence"
        return d / f"{cycle_id}_{utc_now_iso_compact()}.json"

    def latest_symlink_path(self, rule_path: Path, cycle_id: str) -> Path:
        d = self.compute_enrichment_dir(rule_path) / "evidence"
        return d / f"{cycle_id}_latest.symlink"

    def write(
        self,
        rule_path: Path,
        cycle_id: str,
        rule_data: dict,
        rule_sha256_before: str,
        rule_sha256_after: str,
        source_meta: dict,
        raw_data: Any,
        applied_diff: dict,
        summary: dict,
        applied_by: str = "liaprobe-rule-enrich/v2.0",
        session: str | None = None,
    ) -> tuple[Path, str]:
        """Write an evidence file + update symlink. Returns (evidence_path, evidence_sha256)."""
        evidence_dir = self.compute_enrichment_dir(rule_path) / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        ev_path = self.evidence_path(rule_path, cycle_id)
        raw_data_sha = sha256_canonical_json(raw_data)
        applied_diff_sha = sha256_canonical_json(applied_diff)
        evidence = {
            "$schema": self.SCHEMA_VERSION,
            "cycle": cycle_id.removeprefix("cycle_"),  # "4_cve" not "cycle_4_cve"
            "rule": {
                "id": rule_data.get("id"),
                "path": str(rule_path),
                "rule_sha256": rule_sha256_before,
                "rule_sha256_after": rule_sha256_after,
            },
            "applied_at": utc_now_iso(),
            "applied_by": applied_by,
            "session": session,
            "source": source_meta,
            "raw_data": raw_data,
            "raw_data_sha256": raw_data_sha,
            "raw_data_size_bytes": len(json.dumps(raw_data, ensure_ascii=False)),
            "applied_diff": applied_diff,
            "applied_diff_sha256": applied_diff_sha,
            "summary": summary,
            "validation": {
                "input_schema_pass": True,
                "output_schema_pass": True,
                "regex_preserved": True,
            },
        }
        SchemaValidator.validate_evidence(evidence)
        AtomicJSONWriter.write(ev_path, evidence)
        ev_sha = sha256_file(ev_path)

        # Update symlink atomically
        self._update_symlink(self.latest_symlink_path(rule_path, cycle_id), ev_path.name)
        return ev_path, ev_sha

    @staticmethod
    def _update_symlink(symlink_path: Path, target_name: str) -> None:
        """Atomically update symlink to point to target_name (relative)."""
        symlink_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = symlink_path.with_suffix(symlink_path.suffix + ".tmp")
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        os.symlink(target_name, str(tmp))
        os.replace(str(tmp), str(symlink_path))

    def verify_integrity(self, evidence_path: Path) -> bool:
        """Return True if evidence raw_data_sha256 matches actual content."""
        ev = json.loads(evidence_path.read_text(encoding="utf-8"))
        computed = sha256_canonical_json(ev["raw_data"])
        return computed == ev["raw_data_sha256"]


# ======================================================================
# Path resolution helpers
# ======================================================================

def find_liaprobe_root() -> Path:
    """Find the LiaProbe repo root by walking up from current file."""
    # Default: /opt/lia-sec/liaprobe (configurable via env)
    env_root = os.environ.get("LIAPROBE_ROOT")
    if env_root:
        p = Path(env_root)
        if p.exists():
            return p
    # Search upward for marker
    candidates = [
        Path("/opt/lia-sec/liaprobe"),
        Path.cwd(),
    ]
    for c in candidates:
        if (c / "data" / "fingerprints").exists():
            return c.resolve()
    raise EnrichError("Cannot locate LiaProbe root (set LIAPROBE_ROOT env)")


def find_tracking_root() -> Path:
    """Find the enrichment v2 tracking root.

    Resolution order:
    1. env LIAPROBE_ENRICH_ROOT (explicit override)
    2. /opt/lia-sec/dev/_alire/tracking/liaprobe-enrich-v2 (committed in LIA-SEC dev)
    3. liaprobe_root/_alire/tracking/liaprobe-enrich-v2 (legacy local-only path)
    """
    env_root = os.environ.get("LIAPROBE_ENRICH_ROOT")
    if env_root:
        p = Path(env_root).resolve()
        if p.exists():
            return p
    dev_path = Path("/opt/lia-sec/dev/_alire/tracking/liaprobe-enrich-v2")
    if dev_path.exists():
        return dev_path
    return find_liaprobe_root() / "_alire" / "tracking" / "liaprobe-enrich-v2"


# ======================================================================
# Module exports
# ======================================================================

__all__ = [
    # Exceptions
    "EnrichError",
    "InvalidInputError",
    "DependencyMissingError",
    "LockContentionError",
    "TamperDetectedError",
    "DriftCriticalError",
    # Helpers
    "utc_now_iso",
    "utc_now_iso_compact",
    "sha256_bytes",
    "sha256_string",
    "sha256_canonical_json",
    "sha256_file",
    "sha1_path",
    # Classes
    "AtomicJSONWriter",
    "LockManager",
    "SchemaValidator",
    "HTTPClient",
    "HTTPResponse",
    "PGClient",
    "CanonicalVendorResolver",
    "extract_cpe_vendor",
    "extract_cpe_product",
    "_cpe_part_classify",
    "_parse_cpe",
    "VENDOR_FUZZY_THRESHOLD",
    "RUNTIME_NOISE_VENDORS",
    "PROTOCOL_NOISE_TOKENS",
    "TAXONOMY_NOISE_FIRST_TOKENS",
    "is_runtime_noise",
    "is_protocol_noise",
    "is_taxonomy_noise",
    "StructuredLogger",
    "StateManager",
    "CycleStatus",
    "EvidenceWriter",
    # Constants
    "CYCLES",
    "LIA_FINGERPRINT_SCHEMA",
    "LIA_EVIDENCE_SCHEMA",
    # Path helpers
    "find_liaprobe_root",
    "find_tracking_root",
]
