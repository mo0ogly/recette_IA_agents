"""Pure named-wire enrichment for the eBPF surface (v1).

The broker captures outbound connects as ``connect:ip:port`` tokens. This module
maps each endpoint back to a DECLARED server (the server registry / private DNS
names) so the cockpit shows ``gh-mock (127.0.0.1:9101)`` instead of a bare IP,
and flags a connect to an UNDECLARED host as a hardened ghost signal. Pure (I4):
no clock, no random, stable ordering -- byte-stable on replay. It NEVER changes
the detection verdict; it annotates alongside it.
"""

from __future__ import annotations

from urllib.parse import urlsplit

_DEFAULT_HTTPS_PORT = 443


def build_endpoint_map(servers: list[dict]) -> dict[str, str]:
    """Map ``"host:port" -> server id`` from the server registry. mock_local ->
    loopback ``127.0.0.1:{port}``; declared_url/real_saas -> the URL host:port
    (default 443 for https). Stable, deterministic."""
    out: dict[str, str] = {}
    for server in servers:
        sid = str(server.get("id") or "")
        if not sid:
            continue
        mode = server.get("mode")
        if mode == "mock_local" and server.get("port"):
            out[f"127.0.0.1:{int(server['port'])}"] = sid
        else:
            url = server.get("url")
            if not url:
                continue
            parts = urlsplit(url if "//" in url else f"//{url}")
            host = parts.hostname
            if not host:
                continue
            port = parts.port or _DEFAULT_HTTPS_PORT
            out[f"{host}:{port}"] = sid
    return out


def annotate_connect(token: str, endpoint_map: dict[str, str]) -> dict:
    """Annotate one surface token. A ``connect:host:port`` token resolves to a
    declared server name or is flagged ``undeclared``; any other token (exec,
    future surfaces) passes through un-flagged. Never raises."""
    if not token.startswith("connect:"):
        return {"raw": token, "name": None, "undeclared": False}
    endpoint = token[len("connect:") :]
    name = endpoint_map.get(endpoint)
    return {"raw": token, "name": name, "undeclared": name is None}


def annotate_recording(recording: dict, servers: list[dict]) -> dict:
    """Per-agent named wire annotations + the run-level undeclared-host list.
    Pure, deterministic, fail-safe (a malformed recording -> empty annotation)."""
    endpoint_map = build_endpoint_map(servers)
    wire_named: dict[str, list[dict]] = {}
    undeclared: list[str] = []
    for rec in recording.get("recordings", []) or []:
        agent_id = str(rec.get("agent_id") or "")
        tokens = (rec.get("surfaces") or {}).get("ebpf_wire") or []
        anns = [annotate_connect(str(t), endpoint_map) for t in tokens]
        if agent_id:
            wire_named[agent_id] = anns
        for ann in anns:
            if ann["undeclared"]:
                undeclared.append(ann["raw"][len("connect:") :])
    return {"wire_named": wire_named, "undeclared_hosts": sorted(set(undeclared))}
