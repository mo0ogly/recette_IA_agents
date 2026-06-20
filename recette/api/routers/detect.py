"""GET /detect/signatures + POST /detect/scan -- static "reperage" of
agent-observability tooling in a source, surfaced to the console.

This is the DISCOVERY-side detector: given the text of a source, it reports
which agent/LLM observability tools it uses (tracing / replay / audit / eval /
gateway), by matching a committed table of PUBLIC identifiers -- package names,
import paths, environment-variable keys, call markers. The signature table is
the recette's OWN data, loaded from a single committed JSON file (never
duplicated here): ``corpus/detect/observability-signatures.json``. The path is
config-first (R5), overridable via env, defaulting to the corpus file resolved
from the repo root.

This endpoint AGREES byte-for-byte with the Rust reference detector
(``discoveryprobe/discoveryprobe-detect``): for each signature in FILE ORDER, if
any needle is a substring of the text, emit one match (tool, category, the first
needle that matched); then sort the matches by tool name ascending. One match
per tool.

Determinism (I4): both routes are pure functions of their inputs (the loaded
table is sorted/iterated in a fixed order); no clock, no randomness, so the same
text yields a byte-stable report.

Fail-safe: a missing, unreadable, or malformed signatures file yields an EMPTY
catalog (no tools, no matches) with a logged warning -- never a 500.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/detect", tags=["detect"])

logger = logging.getLogger(__name__)

_SIGNATURES_ENV = "INSPECT_IA_AGENTS_DETECT_SIGNATURES"
_DEFAULT_SIGNATURES_REL = "corpus/detect/observability-signatures.json"
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _signatures_path() -> Path:
    """The observability-signatures path. Config first (R5): overridable via env,
    never a magic literal in the request path; defaults to the committed corpus
    file resolved from the repo root."""
    raw = os.environ.get(_SIGNATURES_ENV)
    if raw:
        return Path(raw)
    return _REPO_ROOT / _DEFAULT_SIGNATURES_REL


def _load_signatures() -> list[dict[str, object]]:
    """Load the signature table, fail-safe to an empty list on any error.

    Returns the entries in FILE ORDER (the detector relies on it). Each kept
    entry has a string ``tool``, a string ``category``, a sorted list of string
    ``capabilities`` (defaulting to ``[category]`` when the source omits it), and
    a list of string ``needles``; anything malformed is skipped, never raised.
    """
    path = _signatures_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("detect signatures unreadable at %s: %s -> empty table", path, exc)
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("detect signatures malformed at %s: %s -> empty table", path, exc)
        return []
    if not isinstance(parsed, list):
        logger.warning("detect signatures not an array at %s -> empty table", path)
        return []

    table: list[dict[str, object]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        tool = entry.get("tool")
        category = entry.get("category")
        needles_raw = entry.get("needles")
        if not isinstance(tool, str) or not isinstance(category, str):
            continue
        if not isinstance(needles_raw, list):
            continue
        needles = [n for n in needles_raw if isinstance(n, str)]
        capabilities_raw = entry.get("capabilities")
        if isinstance(capabilities_raw, list):
            capabilities = sorted({c for c in capabilities_raw if isinstance(c, str)})
        else:
            capabilities = [category]
        table.append(
            {
                "tool": tool,
                "category": category,
                "capabilities": capabilities,
                "needles": needles,
            }
        )
    return table


def _detect(text: str, table: list[dict[str, object]]) -> list[dict[str, str]]:
    """Replicate the Rust ``detect`` algorithm exactly.

    For each signature in FILE ORDER, the first needle that is a substring of
    ``text`` flags the tool (one match per tool). The matches are then sorted by
    tool name ascending. Pure and deterministic (I4).
    """
    matches: list[dict[str, str]] = []
    for entry in table:
        tool = str(entry["tool"])
        category = str(entry["category"])
        needles = entry["needles"]
        if not isinstance(needles, list):
            continue
        for needle in needles:
            if isinstance(needle, str) and needle in text:
                matches.append({"tool": tool, "category": category, "matched": needle})
                break
    matches.sort(key=lambda match: match["tool"])
    return matches


class ScanRequest(BaseModel):
    """The scan body: the source text to inspect for observability tooling."""

    text: str = ""


@router.get("/signatures")
def signatures() -> dict:
    """The catalog of observability tools we can detect.

    Returns ``{tools: [{tool, category, capabilities[], needles[]}], categories:
    [sorted distinct]}``. ``capabilities`` is sorted and defaults to
    ``[category]`` when the source omits it. Tools are in file order. Fail-safe:
    an absent/unreadable/malformed signatures file returns empty ``tools`` +
    ``categories``.
    """
    table = _load_signatures()
    categories = sorted({str(entry["category"]) for entry in table})
    return {"tools": table, "categories": categories}


@router.post("/scan")
def scan(body: ScanRequest) -> dict:
    """Detect the observability tools present in ``body.text``.

    Returns ``{matches: [{tool, category, matched}]}`` -- one match per tool (the
    first needle that hits), sorted by tool name. Agrees byte-for-byte with the
    Rust reference detector. Fail-safe: an empty/bad signatures file yields no
    matches; a clean text yields no matches.
    """
    return {"matches": _detect(body.text, _load_signatures())}
