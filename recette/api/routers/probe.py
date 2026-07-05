"""POST /probe/capture -- relay a bounded eBPF capture to the broker, score it.

NON-privileged (design sec. 7). The route relays a `capture` command to the
discoveryprobe broker over its local Unix socket
(``INSPECT_IA_AGENTS_PROBE_SOCKET``), returns the broker recording, and -- when
the capture succeeded -- the ``DetectionScorecard`` from the same source-agnostic
judge (``recette/surface``). The console Probe view consumes this. The API holds
no privilege; the broker holds CAP_BPF.

Fail-safe: no socket configured or broker unreachable -> 503, never a fabricated
capture.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess  # nosec B404 - fixed binary + fixed args, no shell, no request input
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ...inventory_bridge import parse_inventory
from ...surface.agent_analysis import analyze_recording, declared_view
from ...surface.netmap import annotate_recording
from ...surface.recording import score_recording
from ..probe_relay import ProbeUnavailable, relay_capture

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/probe", tags=["probe"])

#: Committed sample ``AgentInventory`` served by ``GET /probe/inventory``. It is
#: assembled from REAL ``discoveryprobe-inventory`` CLI output (Task 5): the
#: present block + comm graph come from a real ``scan ... --capture`` run, the
#: absent and invalid blocks are the real single-agent scan fixtures
#: (tests/fixtures/agent_inventory*.fixture.json). Merging real per-agent blocks
#: into one document is the sanctioned way to obtain a captured API sample that
#: exercises all three passport states -- the CLI scans one agent per tree, so a
#: multi-agent inventory is never a single CLI run. repo_root is this file's
#: parents[3] (recette/api/routers/probe.py -> repo root), matching sim.py.
_INVENTORY_SAMPLE = (
    Path(__file__).resolve().parents[3] / "corpus" / "inventory" / "sample-inventory.json"
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: The compiled ``discoveryprobe-inventory`` CLI, produced by
#: ``./recette.sh discovery-build``. Config first (R5): env override, else the
#: release build under the discoveryprobe workspace.
_INVENTORY_BIN_ENV = "INSPECT_IA_AGENTS_INVENTORY_BIN"
_INVENTORY_BIN_REL = "discoveryprobe/target/release/discoveryprobe-inventory"

#: Root of real agent-source trees the live scan walks. Each immediate child that
#: contains a ``repo/`` directory is scanned as one agent-source tree. Config
#: first (R5): env override, else the discovery corpus repos.
_INVENTORY_SCAN_ROOT_ENV = "INSPECT_IA_AGENTS_INVENTORY_SCAN_ROOT"
_INVENTORY_SCAN_ROOT_REL = "corpus/repos"

#: Corpus trust file (``{ "<key_id>": "<pubkey_hex>", ... }``) fed to the scan's
#: ``--trust`` flag so a signed ``passport.json`` can verify to ``trusted``. When
#: this file is absent the scan runs WITHOUT ``--trust``/``--now`` and a present
#: passport is the fail-safe ``untrusted`` (unknown key) -- never crashes (R7).
_INVENTORY_TRUST_REL = "corpus/keys/test-authority.trust.json"

#: Injected reference clock for the attestation expiry check (I4/R5). This is an
#: operator-facing LIVE scan, not a judged decision path, but the clock is kept a
#: fixed injected CONSTANT (never ``datetime.now()``) so the same corpus yields
#: the same attestation verdicts. Env-overridable for an operator who needs to
#: probe expiry at a different reference instant.
_INVENTORY_NOW_ENV = "INSPECT_IA_AGENTS_INVENTORY_NOW"
_DEFAULT_INVENTORY_NOW = "2027-01-01T00:00:00Z"

_INVENTORY_ENGINE = "discoveryprobe-inventory (Rust)"


def _inventory_bin() -> Path:
    raw = os.environ.get(_INVENTORY_BIN_ENV)
    return Path(raw) if raw else _REPO_ROOT / _INVENTORY_BIN_REL


def _inventory_scan_root() -> Path:
    raw = os.environ.get(_INVENTORY_SCAN_ROOT_ENV)
    return Path(raw) if raw else _REPO_ROOT / _INVENTORY_SCAN_ROOT_REL


def _inventory_trust() -> Path:
    """The corpus trust file (repo-root-relative, like ``_inventory_scan_root``).

    No env override: the trust anchor is a fixed corpus artifact, not an operator
    knob. Its presence is what enables the signed-attestation axis on the scan."""
    return _REPO_ROOT / _INVENTORY_TRUST_REL


def _inventory_now() -> str:
    """The injected reference clock for attestation expiry (config-first, R5).

    Env override, else the documented default constant -- fixed, never the wall
    clock, so the live scan's attestation verdicts stay deterministic (I4)."""
    return os.environ.get(_INVENTORY_NOW_ENV) or _DEFAULT_INVENTORY_NOW


def _scan_one_tree(binary: Path, tree: Path) -> dict | None:
    """Run the Rust inventory engine on one agent-source tree, return its
    ``AgentInventory`` dict, or ``None`` if the scan fails.

    Fixed binary path + fixed tree path, no shell, no request input (the tree
    comes from the configured scan root, and the trust path + reference clock come
    from config -- never from the caller). When the corpus trust file exists the
    scan is invoked with ``--trust <file> --now <reference>`` so a signed
    ``passport.json`` can resolve its attestation (trusted/untrusted); when it is
    absent the scan runs without those flags and a present passport becomes the
    fail-safe untrusted (unknown key), never crashing (R7). Fail-safe: any failure
    (non-zero exit, timeout, non-JSON) returns ``None`` so one bad tree never fails
    the whole scan.
    """
    argv = [str(binary), "scan", str(tree)]
    trust = _inventory_trust()
    if trust.is_file():
        argv += ["--trust", str(trust), "--now", _inventory_now()]
    try:
        proc = subprocess.run(  # nosec B603
            argv,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("inventory scan of %s failed to run: %s", tree, exc)
        return None
    if proc.returncode != 0:
        logger.warning("inventory scan of %s exited %s", tree, proc.returncode)
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        logger.warning("inventory scan of %s returned non-JSON: %s", tree, exc)
        return None


def _merge_inventories(docs: list[dict]) -> dict:
    """Merge per-tree ``AgentInventory`` documents into one live inventory.

    Agents are concatenated and sorted by ``agent_id``; comm-graph edge lists are
    unioned and de-duplicated; the summary is recomputed from the merged agents.
    Deterministic given the input set (sorted throughout, I4-friendly): this is an
    operator-facing live scan, not a judged decision path.
    """
    agents: list[dict] = []
    for doc in docs:
        agents.extend(doc.get("agents", []))
    agents.sort(key=lambda a: a.get("agent_id", ""))

    edge_keys = ("declared_edges", "observed_edges", "undeclared_edges", "via_gateway_edges")
    comm: dict[str, list[dict]] = {}
    for key in edge_keys:
        seen: list[dict] = []
        for doc in docs:
            for edge in doc.get("comm_graph", {}).get(key, []):
                if edge not in seen:
                    seen.append(edge)
        seen.sort(key=lambda e: (e.get("from", ""), e.get("to", "")))
        comm[key] = seen

    def _violations(agent: dict) -> int:
        conf = agent.get("conformity", {})
        return len(conf.get("violations", [])) if conf.get("kind") == "violations" else 0

    def _attested(kind: str) -> int:
        return sum(1 for a in agents if a.get("attestation", {}).get("kind") == kind)

    summary = {
        "with_passport": sum(1 for a in agents if a.get("passport", {}).get("kind") == "present"),
        "without_passport": sum(1 for a in agents if a.get("passport", {}).get("kind") == "absent"),
        "invalid_passport": sum(
            1 for a in agents if a.get("passport", {}).get("kind") == "invalid"
        ),
        "violation_count": sum(_violations(a) for a in agents),
        # Signed-credential (attestation) axis, orthogonal to the manifest counters
        # above. Counted by each agent's ``attestation.kind`` (trusted/untrusted/
        # unsigned/malformed) which the scan emits per record and the concat passes
        # through untouched.
        "attested_trusted": _attested("trusted"),
        "attested_untrusted": _attested("untrusted"),
        "unsigned": _attested("unsigned"),
        "attested_malformed": _attested("malformed"),
    }
    return {
        "schema_version": "1.0",
        "agents": agents,
        "comm_graph": comm,
        "summary": summary,
    }


def _live_inventory() -> dict | None:
    """Scan every configured agent-source tree with the Rust engine and merge the
    results into one live ``AgentInventory``. Returns ``None`` when the binary is
    not built or no tree could be scanned (the caller then falls back to the
    committed sample)."""
    binary = _inventory_bin()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return None
    root = _inventory_scan_root()
    if not root.is_dir():
        return None
    docs: list[dict] = []
    for child in sorted(root.iterdir()):
        tree = child / "repo"
        if tree.is_dir():
            doc = _scan_one_tree(binary, tree)
            if doc is not None:
                _relabel_bland_ids(doc, slug=child.name, mount=tree.name)
                docs.append(doc)
    if not docs:
        return None
    return _merge_inventories(docs)


def _relabel_bland_ids(doc: dict, *, slug: str, mount: str) -> None:
    """Replace an agent id derived from the generic mount directory (e.g. ``repo``)
    with the subject slug, so a shadow/invalid agent scanned at ``<slug>/repo``
    reads as ``<slug>`` in the console instead of a bland, collision-prone
    ``repo``. Passport-present agents carry a real declared id and are untouched.
    """
    for agent in doc.get("agents", []):
        if agent.get("agent_id") == mount:
            agent["agent_id"] = slug


def _attach_wire_names(result: dict, request: Request) -> dict:
    """Attach the v1 named-wire annotation AND the discovery's per-agent analysis
    (the discovery's job: PLANNED vs SAID vs DONE coherence + logging
    recommendations) to a capture result. Pure/fail-safe: never changes the
    scorecard, never raises. config_store is the server registry source."""
    recording = result.get("recording")
    if not isinstance(recording, dict):
        return result
    store = request.app.state.config_store
    servers = store.list_servers()
    annotated = annotate_recording(recording, servers)
    result.update(annotated)
    # The discovery's job: for every agent seen, compare what it was PLANNED to do
    # (declared scope + systems) vs what it DID (the kernel wire) and recommend what
    # to log, so the integrated console can report it in detail.
    # declared_view derives the PLANNED set (bound server id, not target_system) and
    # cables SAID (decided action_types) from each agent's scenario -- pure (I4),
    # tested in tests.test_agent_analysis without importing this router.
    declared_by_agent: dict[str, dict] = {
        str(agent_id): declared_view(store.get_agent(str(agent_id)) or {})
        for agent_id in annotated.get("wire_named", {})
    }
    result["agent_analysis"] = analyze_recording(annotated, declared_by_agent=declared_by_agent)
    return result


_SOCKET_ENV = "INSPECT_IA_AGENTS_PROBE_SOCKET"
_MODE_ENV = "INSPECT_IA_AGENTS_PROBE_MODE"
_MAX_DURATION_ENV = "INSPECT_IA_AGENTS_PROBE_MAX_DURATION_MS"
_DEFAULT_MAX_DURATION_MS = 30_000


def _canonical_socket() -> Path:
    """The launcher's canonical broker socket: ``<repo_root>/.run/probe.sock``.

    Mirrors ``PROBE_SOCKET_PATH`` in ``cicd/lib/common.sh`` (``${RUN_DIR}/probe.sock``).
    repo_root is this file's grandparent's-parent: recette/api/routers/probe.py.
    """
    return Path(__file__).resolve().parent.parent.parent.parent / ".run" / "probe.sock"


def _canonical_mode(default: str) -> str:
    """Mode of the launcher's canonical broker, read from ``.run/probe.mode``.

    The launcher writes ``live`` there when it started the privileged CAP_BPF
    broker on the canonical socket, ``replay`` for the non-privileged one. Read
    it so ``/probe/status`` tells the truth (R13/R14: never claim live for a
    replay broker, never hide a real live one). Falls back to ``default`` when
    the file is absent/unreadable (a hand-started broker without the marker)."""
    mode_file = _canonical_socket().with_name("probe.mode")
    try:
        value = mode_file.read_text(encoding="utf-8").strip()
    except OSError:
        return default
    return value if value in ("live", "replay") else default


def _resolve_socket() -> tuple[str | None, str]:
    """Resolve the broker socket and its mode (config-first, R5/R18).

    1. ``INSPECT_IA_AGENTS_PROBE_SOCKET`` env wins (mode from ``..._PROBE_MODE``,
       default ``live`` -- an operator-set socket targets the privileged broker).
    2. Fallback: the launcher's canonical ``.run/probe.sock`` IF it exists as a
       socket. This closes the friction where a standalone ``api restart`` (e.g.
       from a concurrent session) drops the env while the auto-started broker is
       still up -- the probe stays usable instead of going dark. Its mode comes
       from ``.run/probe.mode`` (the launcher records live vs replay there), so a
       launcher-started LIVE broker on the canonical socket reports ``live`` while
       the default replay broker reports ``replay`` (R13/R14).
    3. Otherwise: no socket -> ``(None, "off")``.
    """
    env_socket = os.environ.get(_SOCKET_ENV)
    if env_socket:
        return env_socket, os.environ.get(_MODE_ENV, "live")
    canonical = _canonical_socket()
    if canonical.is_socket():
        return str(canonical), _canonical_mode(os.environ.get(_MODE_ENV, "replay"))
    return None, "off"


def _max_duration_ms() -> int:
    """The API-side friendly cap (the broker manifest is the real bound). Config
    first (R5): overridable via env, never a magic literal in the request path."""
    raw = os.environ.get(_MAX_DURATION_ENV)
    if raw is None:
        return _DEFAULT_MAX_DURATION_MS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_DURATION_MS
    return value if value > 0 else _DEFAULT_MAX_DURATION_MS


@router.get("/status")
def status() -> dict:
    """Whether the probe broker socket is configured (for the console to enable
    the capture button). Does not connect -- reachability is proven by a capture.

    ``mode`` is ``replay`` when a non-privileged replay broker is wired (dev/CI,
    deterministic replay of corpus surface ground-truth) and ``live`` when the
    privileged eBPF broker is expected (CAP_BPF). It is surfaced so the console
    never presents a replay as a live capture (R13/R14). Config-first (R5).

    Resolves the env socket first, then the launcher's canonical ``.run/probe.sock``
    fallback, so a probe stays usable when a standalone ``api restart`` dropped the
    env but the auto-started broker is still up."""
    socket_path, mode = _resolve_socket()
    return {
        "configured": socket_path is not None,
        "socket_env": _SOCKET_ENV,
        "mode": mode,
    }


@router.get("/inventory")
def inventory() -> dict:
    """Serve a LIVE ``AgentInventory`` for the console panel: the Rust engine
    scans every configured agent-source tree on demand and the results are merged.

    Read-only (I1): the scan only reads source trees, it mediates nothing. The
    live scan runs the compiled ``discoveryprobe-inventory`` binary (fixed path +
    fixed tree paths from config, no shell, no request input), exactly like the
    catalog ``/rust-summary`` engine bridge. Each per-tree scan is byte-stable
    (I4); merging is done in sorted order, so the same corpus yields the same
    inventory -- this is an operator-facing live scan, not a judged decision path.

    Fail-safe (R7): if the binary is not built, no tree scans, or the scan output
    is unusable, the route falls back to the committed sample and flags
    ``live: false`` with a reason -- the panel still renders, and the operator
    knows it is the sample, not a live scan. The response is
    ``{inventory, live, engine, reason?}`` wrapped so the client unwraps one key.
    """
    live = _live_inventory()
    if live is not None:
        return {"inventory": live, "live": True, "engine": _INVENTORY_ENGINE}

    # Fallback: the Rust engine is not built (or nothing scanned). Serve the
    # committed sample so the panel still renders, flagged as not-live.
    reason = (
        "live scan unavailable (build via ./recette.sh discovery-build; "
        f"scans {_INVENTORY_SCAN_ROOT_REL})"
    )
    try:
        raw = _INVENTORY_SAMPLE.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"live scan unavailable and sample missing at {_INVENTORY_SAMPLE.name}",
        ) from exc
    # Validate the shape through the bridge boundary; a broken sample is a loud
    # 500, never a silently served malformed document.
    try:
        parse_inventory(raw)
        parsed = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"sample inventory malformed: {exc}") from exc
    return {"inventory": parsed, "live": False, "engine": _INVENTORY_ENGINE, "reason": reason}


_MANIFEST_ENV = "INSPECT_IA_AGENTS_PROBE_MANIFEST"


def _manifest_agents() -> list[str]:
    """Agent ids in the broker manifest (the watch-list). Reads
    ``INSPECT_IA_AGENTS_PROBE_MANIFEST`` then the launcher's canonical
    ``.run/probe-manifest.json``. Empty/absent -> []. Fail-safe (never raises)."""
    candidates = []
    env_path = os.environ.get(_MANIFEST_ENV)
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(_canonical_socket().with_name("probe-manifest.json"))
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        agents = data.get("agents") if isinstance(data, dict) else None
        if isinstance(agents, dict):
            return sorted(agents)
    return []


@router.get("/monitor")
def monitor_status(request: Request) -> dict:
    """Live state of the passive eBPF watch: running?, window, and the rolling
    sightings (agents seen on the wire, with their surfaces). Read-only."""
    return request.app.state.probe_monitor.snapshot()


@router.post("/monitor/start")
def monitor_start(request: Request, body: dict[str, Any]) -> dict:
    """Start the passive watch: a background loop of back-to-back broker captures
    over the watch-list, so any watched agent that runs is flagged in
    near-real-time. ``agents`` defaults to every configured agent id (the broker
    manifest is the real allowlist). 503 when no broker socket is configured."""
    socket_path, mode = _resolve_socket()
    if not socket_path:
        raise HTTPException(status_code=503, detail=f"{_SOCKET_ENV} not set and no broker socket")
    agents = body.get("agents")
    if not isinstance(agents, list) or not agents:
        # Default watch-list = the broker MANIFEST agents (the broker rejects a
        # capture naming any non-manifest agent, so we never watch beyond it).
        agents = _manifest_agents()
    if not agents:
        raise HTTPException(
            status_code=400,
            detail="no agents to watch (set a broker manifest or pass agents)",
        )
    window_ms = body.get("window_ms", 2000)
    if not isinstance(window_ms, int) or isinstance(window_ms, bool) or window_ms <= 0:
        raise HTTPException(status_code=400, detail="window_ms must be a positive integer")
    started = request.app.state.probe_monitor.start(
        socket_path=socket_path, agents=agents, window_ms=window_ms
    )
    return {"started": started, "mode": mode, "agents": agents}


@router.post("/monitor/stop")
def monitor_stop(request: Request) -> dict:
    """Stop the passive watch (idempotent)."""
    request.app.state.probe_monitor.stop()
    return {"running": False}


@router.post("/process-capture")
def process_capture(request: Request, body: dict[str, Any]) -> dict:
    """Spawn an agent as its own process and capture it by PID (precise eBPF).

    The launcher knows the spawned child's pid, so the broker attributes by that
    exact pid -- no reliance on the 15-byte ``comm``. Mock-only (a live key never
    crosses the subprocess). 503 when no broker socket; 400 on a bad agent."""
    socket_path, _ = _resolve_socket()
    if not socket_path:
        raise HTTPException(status_code=503, detail=f"{_SOCKET_ENV} not set and no broker socket")
    store = request.app.state.config_store
    agent_cfg = store.get_agent(str(body.get("agent_id", "")))
    if agent_cfg is None:
        raise HTTPException(status_code=400, detail="unknown agent_id")
    if agent_cfg.get("ai_mode", "mock") == "real":
        raise HTTPException(status_code=400, detail="process-capture is mock-only")
    if not agent_cfg.get("scenario"):
        raise HTTPException(status_code=400, detail="process-capture needs a mock scenario")
    duration_ms = body.get("duration_ms", 3000)
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms <= 0:
        raise HTTPException(status_code=400, detail="duration_ms must be a positive integer")
    from ..probe_relay import ProbeUnavailable
    from ..runners import run_process_capture

    try:
        return _attach_wire_names(
            run_process_capture(
                agent_cfg, store.list_servers(), socket_path=socket_path, duration_ms=duration_ms
            ),
            request,
        )
    except ProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/process-capture-campaign")
def process_capture_campaign(request: Request, body: dict[str, Any]) -> dict:
    """Spawn every step of a campaign as its own process and capture them by PID.

    The campaign analogue of ``/process-capture``: the discovery operator picks a
    campaign and the launcher runs all its mock-capable agents as OS processes in
    one eBPF capture window, attributing each by its exact child pid. Returns the
    aggregate broker recording + ``DetectionScorecard`` (an agent captured on no
    surface is a GHOST in ``false_negatives``) plus the ``skipped`` steps (real /
    no-scenario, never faked). 503 when no broker socket; 400 on a bad campaign.
    """
    socket_path, _ = _resolve_socket()
    if not socket_path:
        raise HTTPException(status_code=503, detail=f"{_SOCKET_ENV} not set and no broker socket")
    store = request.app.state.config_store
    campaign = request.app.state.campaign_store.get(str(body.get("campaign_id", "")))
    if campaign is None:
        raise HTTPException(status_code=400, detail="unknown campaign_id")
    duration_ms = body.get("duration_ms", 4000)
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms <= 0:
        raise HTTPException(status_code=400, detail="duration_ms must be a positive integer")
    from ..probe_relay import ProbeUnavailable
    from ..runners import run_campaign_process_capture

    try:
        return _attach_wire_names(
            run_campaign_process_capture(
                campaign,
                store,
                store.list_servers(),
                socket_path=socket_path,
                duration_ms=duration_ms,
            ),
            request,
        )
    except ProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/capture")
def capture(request: Request, body: dict[str, Any]) -> dict:
    """Relay one bounded capture to the broker and score the recording.

    Body: ``{"agents": [ids], "duration_ms": <int>}``. Validation here mirrors
    the broker (deny-by-default lives in the broker; this is the friendly 400):
    a non-empty agent list of strings, a positive bounded duration.
    """
    socket_path, _ = _resolve_socket()
    if not socket_path:
        raise HTTPException(
            status_code=503,
            detail=f"{_SOCKET_ENV} not set and no broker socket at .run/probe.sock",
        )

    agents = body.get("agents")
    if not isinstance(agents, list) or not agents or not all(isinstance(a, str) for a in agents):
        raise HTTPException(status_code=400, detail="agents must be a non-empty list of ids")
    duration_ms = body.get("duration_ms", 3000)
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms <= 0:
        raise HTTPException(status_code=400, detail="duration_ms must be a positive integer")
    ceiling = _max_duration_ms()
    if duration_ms > ceiling:
        raise HTTPException(
            status_code=400,
            detail=f"duration_ms exceeds the API ceiling {ceiling}",
        )

    try:
        recording = relay_capture(socket_path=socket_path, agents=agents, duration_ms=duration_ms)
    except ProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    out: dict = {"recording": recording}
    if recording.get("status") == "ok":
        out["scorecard"] = asdict(score_recording(json.dumps(recording)))
    return _attach_wire_names(out, request)
