"""Independent SEEN-vs-DONE cross-surface coherence (#10).

The discovery-vs-proxy check (recette_discovery_vs_proxy_skynet.py) feeds the SAME
decided action-log to both sides, so its agreement is partly tautological. This
analyzer crosses two GENUINELY INDEPENDENT observation channels:

  SEEN  -- the eBPF kernel surface: which server the agent actually DIALED
           (`connect:ip:port`), mapped back to a target_system via the server
           registry (netmap.build_endpoint_map). A syscall-level observation the
           agent cannot fake from user space.
  DONE  -- the mediated proxy surface: which target_system the agent EXECUTED
           against (proxy_traces_skynet.jsonl `target_system`). An app-layer
           observation from the governed side-effect path.

These are observed by different mechanisms (kernel tracepoint vs application
proxy), so their agreement is real evidence, not a definition. A divergence is a
finding: a server SEEN dialed but never mediated by the proxy is a potential covert
channel (egress the governance layer did not record); a target DONE but never SEEN
dialed means the side effect did not cross the wire we watch (e.g. an in-memory
forge, expected for non-traced runs).

Pure (I4): reads the recorded logs only, no clock, no random. Run after the eBPF
live capture + the traced pass.
Run: python3 scripts/recette_seen_vs_done_skynet.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_DIR = _ROOT / "docs" / "tracking" / "recette"


def _load_jsonl(name: str) -> list[dict]:
    p = _DIR / name
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _server_system_by_endpoint(servers: list[dict]) -> dict[str, str]:
    """`host:port -> target_system` from the registry (independent of any agent
    log). Built from build_endpoint_map (id) joined to each server's system."""
    from recette.surface.netmap import build_endpoint_map

    id_by_endpoint = build_endpoint_map(servers)
    system_by_id = {str(s.get("id")): str(s.get("system", "")) for s in servers}
    return {ep: system_by_id.get(sid, "") for ep, sid in id_by_endpoint.items()}


def analyze(ebpf: dict, proxy_rows: list[dict], servers: list[dict]) -> dict:
    """Per-agent SEEN (eBPF dialed servers) vs DONE (proxy target_systems). Pure."""
    sys_by_ep = _server_system_by_endpoint(servers)

    seen: dict[str, set[str]] = {}
    seen_unmapped: dict[str, list[str]] = {}
    for cap in ebpf.get("captures", []):
        for a in cap.get("agents", []):
            aid = str(a.get("agent_id") or "")
            for tok in a.get("connects", []):
                ep = tok[len("connect:") :] if tok.startswith("connect:") else tok
                system = sys_by_ep.get(ep)
                if system:
                    seen.setdefault(aid, set()).add(system)
                else:
                    seen_unmapped.setdefault(aid, []).append(ep)

    done: dict[str, set[str]] = {}
    for t in proxy_rows:
        aid = str(t.get("agent_id") or "")
        if t.get("target_system"):
            done.setdefault(aid, set()).add(str(t["target_system"]))

    overlap = sorted(set(seen) & set(done))
    per_agent = []
    agree = 0
    for aid in overlap:
        s, d = seen[aid], done[aid]
        seen_not_done = sorted(s - d)  # dialed but never mediated -> covert-channel signal
        match = s <= d  # every server SEEN dialed was also mediated (no covert egress)
        agree += 1 if match else 0
        per_agent.append(
            {
                "agent_id": aid,
                "seen_systems": sorted(s),
                "done_systems": sorted(d),
                "seen_not_mediated": seen_not_done,
                "coherent": match,
            }
        )
    n = len(overlap) or 1
    # Undeclared egress = any agent that dialed (via eBPF) a host NOT in the registry.
    covert = sorted({ep for eps in seen_unmapped.values() for ep in eps})

    # --- Deterministic kernel-reachability layer (FULL coverage, no caps needed) ---
    # Live process-capture is mock-only (S4: a live key never crosses the captured
    # subprocess), so the LIVE kernel<->action cross only covers the mock agents.
    # For EVERY traced agent, verify deterministically that its DONE target_system
    # maps to a REGISTERED server -- i.e. a kernel-reachable target a live capture
    # COULD witness as a connect. A "ghost target" (a done system with no server)
    # would mean the agent claims to act on a system the kernel could never see --
    # a red flag. This makes the bridge full-coverage; the live overlap is the
    # strong corroboration subset.
    registered_systems = {str(s.get("system")) for s in servers if s.get("system")}
    done_all: dict[str, set[str]] = {}
    for t in proxy_rows:
        aid = str(t.get("agent_id") or "")
        if t.get("target_system"):
            done_all.setdefault(aid, set()).add(str(t["target_system"]))
    reachable_agents: list[dict] = []
    ghost_target_agents: list[dict] = []
    for aid in sorted(done_all):
        systems = sorted(done_all[aid])
        ghosts = [s for s in systems if s not in registered_systems]
        (ghost_target_agents if ghosts else reachable_agents).append(
            {"agent_id": aid, "done_systems": systems, "ghost_targets": ghosts}
        )
    n_done = len(done_all) or 1

    return {
        "overlap_agents": len(overlap),
        "coherent_agents": agree,
        "coherence_rate": round(agree / n, 3),
        "undeclared_egress_endpoints": covert,
        "per_agent": per_agent,
        # Deterministic full-coverage layer:
        "traced_agents": len(done_all),
        "kernel_reachable_agents": len(reachable_agents),
        "kernel_reachable_rate": round(len(reachable_agents) / n_done, 3),
        "ghost_target_agents": ghost_target_agents,
        "note": (
            "TWO tiers. LIVE: SEEN (eBPF kernel connect -> server) vs DONE (proxy "
            "target_system) are INDEPENDENT channels -- real coherence, not the "
            "tautology of one action-log fed to two surfaces; bounded by the mock "
            "agents captured live (process-capture is mock-only, S4). DETERMINISTIC: "
            "every traced agent's DONE target maps to a registered (kernel-reachable) "
            "server, so a ghost-target (a claimed system the kernel could never "
            "witness) is flagged across the WHOLE fleet, no caps needed."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Independent SEEN-vs-DONE cross-surface check.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ebpf_path = _DIR / "ebpf_live_skynet.json"
    ebpf = json.loads(ebpf_path.read_text()) if ebpf_path.exists() else {"captures": []}
    proxy_rows = _load_jsonl("proxy_traces_skynet.jsonl")
    cfg = json.loads((_ROOT / "config" / "inspect_ia_agents.config.json").read_text())
    servers = cfg.get("servers", [])

    result = analyze(ebpf, proxy_rows, servers)
    (_DIR / "seen_vs_done_skynet.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("## SEEN-vs-DONE -- kernel corroborates the agent's action")
        print(
            f"\nLIVE (independent kernel<->action, mock subset): "
            f"{result['coherent_agents']}/{result['overlap_agents']} coherent, "
            f"rate {result['coherence_rate']}"
        )
        for a in result["per_agent"]:
            print(
                f"  {a['agent_id']:38} seen={a['seen_systems']} done={a['done_systems']} "
                f"coherent={a['coherent']}"
            )
        print(
            f"\nDETERMINISTIC (full fleet, no caps): "
            f"{result['kernel_reachable_agents']}/{result['traced_agents']} traced agents have a "
            f"kernel-reachable DONE target, rate {result['kernel_reachable_rate']}"
        )
        ghosts = result["ghost_target_agents"]
        print(
            f"- ghost-target agents (claimed system the kernel could never witness): {len(ghosts)}"
        )
        for g in ghosts:
            print(f"    {g['agent_id']}: ghost_targets={g['ghost_targets']}")
        egress = result["undeclared_egress_endpoints"] or "none"
        print(f"- undeclared egress endpoints (eBPF): {egress}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
