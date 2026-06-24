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
        elif mode in ("declared_url", "real_saas") and server.get("url"):
            # Both URL-backed modes carry a `url` (host[:port]); default to the
            # https port when none is given. urlsplit needs a `//` to find the
            # host, so prepend one for a bare host:port.
            url = str(server["url"])
            parts = urlsplit(url if "//" in url else f"//{url}")
            host = parts.hostname
            if host:
                port = parts.port or _DEFAULT_HTTPS_PORT
                out[f"{host}:{port}"] = sid
    return out


# Declared private-DNS suffixes a `dns:<name>` query may legitimately resolve.
# A DNS query for a name OUTSIDE these is a hardened egress/exfil signal (the DNS
# analogue of the connect ghost-host tripwire). Derived from the server registry's
# declared hostnames; empty when no URL-backed servers are declared.
def _declared_dns_names(servers: list[dict]) -> set[str]:
    names: set[str] = set()
    for server in servers:
        for key in ("fqdn", "url"):
            raw = server.get(key)
            if not raw:
                continue
            text = str(raw)
            parts = urlsplit(text if "//" in text else f"//{text}")
            host = parts.hostname
            if host:
                names.add(host)
        for alias in server.get("aliases", []) or []:
            names.add(str(alias))
    return names


def annotate_connect(token: str, endpoint_map: dict[str, str]) -> dict:
    """Annotate one surface token. A ``connect:host:port`` token resolves to a
    declared server name or is flagged ``undeclared``; any other token (exec,
    future surfaces) passes through un-flagged. Never raises.

    Kept for back-compat; `annotate_token` is the general form that also classifies
    dns/open/fork/exec surfaces (#4)."""
    if not token.startswith("connect:"):
        return {"raw": token, "name": None, "undeclared": False}
    endpoint = token[len("connect:") :]
    name = endpoint_map.get(endpoint)
    return {"raw": token, "name": name, "undeclared": name is None}


def annotate_token(token: str, endpoint_map: dict[str, str], dns_names: set[str]) -> dict:
    """Classify and annotate ANY eBPF-wire token by its kind (#4):

    - ``connect:host:port`` -> resolve to a declared server or flag ``undeclared``
      (the egress tripwire).
    - ``dns:<name>`` -> resolve against the declared private-DNS names or flag
      ``undeclared`` (the DNS exfil tripwire).
    - ``open:/path`` -> classify the path (sys-lib / venv / repo / etc / other) so
      the judge and the noise filter can reason about file access.
    - ``fork:...`` / ``exec:...`` -> a process-lifecycle signal (child spawn / exec).

    Always returns ``{raw, kind, name, undeclared, category}``; never raises."""
    if token.startswith("connect:"):
        endpoint = token[len("connect:") :]
        name = endpoint_map.get(endpoint)
        return {
            "raw": token,
            "kind": "connect",
            "name": name,
            "undeclared": name is None,
            "category": None,
        }
    if token.startswith("dns:"):
        host = token[len("dns:") :]
        known = any(host == n or host.endswith("." + n) for n in dns_names)
        return {
            "raw": token,
            "kind": "dns",
            "name": host if known else None,
            "undeclared": not known,
            "category": None,
        }
    if token.startswith("open:"):
        return {
            "raw": token,
            "kind": "open",
            "name": None,
            "undeclared": False,
            "category": _path_category(token[len("open:") :]),
        }
    if token.startswith("fork:") or token.startswith("exec:"):
        kind = token.split(":", 1)[0]
        return {
            "raw": token,
            "kind": kind,
            "name": None,
            "undeclared": False,
            "category": "process",
        }
    return {"raw": token, "kind": "other", "name": None, "undeclared": False, "category": None}


def _path_category(path: str) -> str:
    """Bucket an open() path so file access is legible to the judge / noise filter
    (#1, #4). Pure string classification."""
    if "site-packages" in path or "/.venv" in path or "dist-packages" in path:
        return "venv"
    if path.startswith(("/usr/", "/lib/", "/lib64/", "/etc/ld.so")):
        return "sys-lib"
    if path.startswith("/etc/"):
        return "etc"
    if "recette" in path or path.startswith("./"):
        return "repo"
    return "other"


def annotate_recording(recording: dict, servers: list[dict]) -> dict:
    """Per-agent named wire annotations + run-level signals across ALL surfaces.
    Pure, deterministic, fail-safe (a malformed recording -> empty annotation).

    Keeps the v1 contract (``wire_named`` per-token list, ``undeclared_hosts``) and
    ADDS (#4): ``undeclared_dns`` (DNS exfil tripwire), ``process_signals`` (per
    agent fork/exec count), and ``surface_summary`` (per-kind token counts) so the
    judge sees dns/open/fork, not only connect."""
    endpoint_map = build_endpoint_map(servers)
    dns_names = _declared_dns_names(servers)
    wire_named: dict[str, list[dict]] = {}
    undeclared: list[str] = []
    undeclared_dns: list[str] = []
    process_signals: dict[str, int] = {}
    summary: dict[str, int] = {}
    for rec in recording.get("recordings", []) or []:
        agent_id = str(rec.get("agent_id") or "")
        tokens = (rec.get("surfaces") or {}).get("ebpf_wire") or []
        anns = [annotate_token(str(t), endpoint_map, dns_names) for t in tokens]
        if agent_id:
            wire_named[agent_id] = anns
        for ann in anns:
            summary[ann["kind"]] = summary.get(ann["kind"], 0) + 1
            if ann["kind"] == "connect" and ann["undeclared"]:
                undeclared.append(ann["raw"][len("connect:") :])
            elif ann["kind"] == "dns" and ann["undeclared"]:
                undeclared_dns.append(ann["raw"][len("dns:") :])
            elif ann["kind"] in ("fork", "exec") and agent_id:
                process_signals[agent_id] = process_signals.get(agent_id, 0) + 1
    return {
        "wire_named": wire_named,
        "undeclared_hosts": sorted(set(undeclared)),
        "undeclared_dns": sorted(set(undeclared_dns)),
        "process_signals": process_signals,
        "surface_summary": dict(sorted(summary.items())),
    }
