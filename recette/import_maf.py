"""Import a Microsoft Agent Framework (MAF) declarative agent spec into the
unified AgentRail recette manifest (the maf_agent family of the merged model).

A MAF declarative agent (``kind: Prompt``) declares ``name`` / ``description`` /
``instructions`` / ``model`` / ``tools`` / ``handoffs``. This importer maps those
faithfully onto ``corpus/schemas/agent-manifest.schema.json`` -- tools keep their
kind and their ``require_approval`` becomes the recette approval expectation
(``always`` => escalate/block, I6). Nothing is fabricated: a tool whose kind is
not a recognized MAF tool kind is reported as a gap rather than guessed into a
capability.

The produced manifest is a DRAFT declaration; the matching action log (what the
agent ACTUALLY does) and ``ground-truth`` (the expected verdict) stay
hand-authored -- the four-dimension judgement lives there, not in the manifest.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# MAF tool kinds the recette models natively, mirrored from agent-spec.schema.json.
MAF_TOOL_KINDS: tuple[str, ...] = (
    "mcp",
    "function",
    "web_search",
    "file_search",
    "code_interpreter",
)

# Provider-hosted tools are identified by their kind alone (no server_url/name);
# mcp and function require an explicit target (server or function name).
_HOSTED_TOOL_KINDS: frozenset[str] = frozenset({"web_search", "file_search", "code_interpreter"})

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_STANDARD = "microsoft-agent-framework"


def slugify(name: str) -> str:
    """Derive an agent_id (``^[a-z0-9][a-z0-9-]{1,63}$``) from a MAF name."""
    slug = _SLUG_STRIP.sub("-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"cannot derive a slug from name {name!r}")
    slug = slug[:64]
    if len(slug) < 2:
        slug = f"{slug}-agent"[:64]
    return slug


def _tool_kind(tool: dict) -> str | None:
    """Read a MAF tool's kind, if recognized.

    The MAF declarative Tool model (agent_framework_declarative._models) keys the
    discriminator on `kind`; older/sample specs used `type`. Both are accepted.
    """
    raw = tool.get("kind") or tool.get("type")
    if isinstance(raw, str) and raw in MAF_TOOL_KINDS:
        return raw
    return None


def _tool_target(tool: dict) -> str:
    """Pick a stable target identifier for a MAF tool, preferring the MCP server.

    Mirrors the real McpTool model fields (`url`, `serverName`) plus the
    sample-spec spellings (`server_url`, `server_label`).
    """
    for key in ("url", "serverName", "server_url", "server_label", "name", "toolName", "id"):
        value = tool.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _approval(tool: dict) -> str:
    """Map a MAF tool's approval requirement to the recette approval expectation.

    The real McpTool carries `approvalMode` as an object whose `kind` is
    `always | never | specify` (McpServerApprovalMode). `specify` requires
    approval for at least some tools, so it is treated as gated (always). Older
    sample specs used a flat `require_approval` string/bool. Absence => never
    (no fabricated policy gate, R13).
    """
    mode = tool.get("approvalMode")
    if isinstance(mode, dict):
        kind = mode.get("kind")
        return "always" if kind in ("always", "specify") else "never"
    raw = tool.get("require_approval")
    return "always" if raw == "always" or raw is True else "never"


def capabilities_from_maf(maf: dict) -> tuple[list[dict], list[str]]:
    """Map MAF tools and handoffs to capability scope entries.

    Returns ``(capability_scope, gaps)``; gaps lists tool entries whose kind was
    not recognized (never invented). Deterministic order and de-duplication (I4).
    """
    scope: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    gaps: list[str] = []

    tools = maf.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if not isinstance(tool, dict):
                gaps.append(repr(tool))
                continue
            kind = _tool_kind(tool)
            target = _tool_target(tool)
            if kind is not None and not target and kind in _HOSTED_TOOL_KINDS:
                target = kind  # hosted tool: identified by its kind
            if kind is None or not target:
                label = tool.get("type") or tool.get("kind") or tool.get("name") or repr(tool)
                gaps.append(str(label))
                continue
            key: tuple[str, ...] = ("invoke_tool", kind, target)
            if key not in seen:
                seen.add(key)
                scope.append(
                    {
                        "action": "invoke_tool",
                        "tool_kind": kind,
                        "target": target,
                        "approval": _approval(tool),
                    }
                )

    for handoff in _handoff_targets(maf):
        key = ("handoff", handoff)
        if key not in seen:
            seen.add(key)
            scope.append({"action": "handoff", "target": handoff})

    return scope, gaps


def _handoff_targets(maf: dict) -> list[str]:
    """Extract handoff/agent target names, tolerating string or object entries."""
    targets: list[str] = []
    for field in ("handoffs", "agents"):
        entries = maf.get(field)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, str) and entry.strip():
                targets.append(entry.strip())
            elif isinstance(entry, dict):
                value = entry.get("name") or entry.get("id") or entry.get("agent")
                if isinstance(value, str) and value.strip():
                    targets.append(value.strip())
    return targets


def maf_to_manifest(maf: dict, *, version: str = "0.1.0") -> tuple[dict, list[str]]:
    """Map a MAF declarative spec to a unified recette manifest draft (kind=maf_agent).

    Returns ``(manifest, gaps)``. The manifest is NOT validated here; the caller
    validates against the manifest schema. ``gaps`` lists MAF tool entries that
    could not be mapped without fabrication.
    """
    name = maf.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("MAF spec has no usable 'name'")

    raw_model = maf.get("model")
    model: dict = raw_model if isinstance(raw_model, dict) else {}
    provider = model.get("provider")
    model_id = model.get("id")
    if not isinstance(provider, str) or not provider.strip():
        # MAF allows omitting provider (inferred from the chat client). The recette
        # needs a declared identity, so this is surfaced rather than guessed.
        raise ValueError("MAF spec model.provider is required to declare identity (I3)")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("MAF spec model.id is required to declare identity (I3)")

    scope, gaps = capabilities_from_maf(maf)
    if not scope:
        raise ValueError(
            "MAF spec declares no mappable tool or handoff; the manifest requires at "
            "least one capability (minItems 1)"
        )

    identity: dict[str, Any] = {"provider": provider.strip(), "model": model_id.strip()}
    connection = model.get("connection")
    if isinstance(connection, dict) and isinstance(connection.get("kind"), str):
        identity["connection_kind"] = connection["kind"].strip()

    # Systems the agent acts on: the provider runtime plus every distinct tool kind.
    targets: list[str] = [slugify(provider)]
    for cap in scope:
        kind = cap.get("tool_kind")
        if kind and kind not in targets:
            targets.append(kind)

    description_parts: list[str] = []
    if isinstance(maf.get("description"), str) and maf["description"].strip():
        description_parts.append(maf["description"].strip())
    if isinstance(maf.get("instructions"), str) and maf["instructions"].strip():
        description_parts.append(f"(MAF instructions) {maf['instructions'].strip()}")

    source: dict[str, Any] = {"standard": _STANDARD}
    if isinstance(maf.get("kind"), str):
        source["maf_kind"] = maf["kind"]

    spec: dict[str, Any] = {
        "kind": "maf_agent",
        "agent_id": slugify(name),
        "name": name.strip(),
        "source": source,
        "target_systems": targets,
        "declared_identity": identity,
        "capability_scope": scope,
        "runtime": {"lab_mode": True, "real_mode": False},
        "version": version,
    }
    if description_parts:
        spec["description"] = " ".join(description_parts)

    return spec, gaps


def load_maf(path: Path) -> dict:
    """Load a MAF declarative spec from a .yaml/.yml or .json file.

    YAML needs the optional ``[maf]`` extra (PyYAML); JSON needs nothing.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ValueError(
                f"reading {path.name} needs PyYAML (pip install 'railgun-recette[maf]'); "
                "or provide the spec as .json"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: MAF spec must be a mapping at the top level")
    return data
