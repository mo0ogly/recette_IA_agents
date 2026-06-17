# Surface-detection recette -- does RailNode SEE the agent?

> The recette (acceptance testing) that proves the thesis: **if the tool does not
> see the agents, it is a failure**. It scores, per observation surface, whether a
> discovery tool (RailNode) detects a simulated agent. An agent detected on NO
> surface turns the scorecard RED. Founding design:
> `docs/plans/2026-06-16-railnode-discovery-recette-host-docker-design.md`.
> Implementation plan: `docs/plans/2026-06-16-railnode-surface-detection.md`.

## The four surfaces

RailNode observes an agent through several interception surfaces (AgentRail RFC):

- `hook_subprocess`, `hook_mcp`, `hook_sdk` -- the inline **hook** family: a shim
  in the agent process sees the structured tool-call (the bench's `ProxyTrace`
  view).
- `ebpf_wire` -- the **eBPF/syscall** family: a kernel probe sees the raw network
  flow (the bench's `WireFlow` view), even across the Docker boundary (one kernel).

## The two views the bench already has

A simulated run yields two deterministic views, reused as-is:

- `proxy_traces` (`recette/platform/proxy/tracing.py::ProxyTrace`) -> the hook view.
- `wire_flows` (`recette/platform/proxy/wire.py::WireFlow`) -> the eBPF/wire view.

`recette/surface/surfaces.py::project_surfaces` maps a run onto every surface
(pure, sorted, I4).

## The ghost keystone

`corpus/surface/ghost-direct-db` is an agent whose native egress bypasses the
SDK: it produces a `wire_flow` but NO `proxy_trace`. So it is **invisible on the
hook surfaces** and **caught only on the wire/eBPF surface**. This is why
per-surface coverage matters: a hook-only detector would miss it. Same
wire-vs-audit duality as `recette/platform/proxy/reconcile.py::reconcile_run`.

## Run it

```
python -m recette surface
```

Prints the detection scorecard (JSON) and exits 0 iff every agent is detected on
at least one surface. Example output (2 subjects):

```
{
  "detected_per_surface": {"ebpf_wire": 2, "hook_mcp": 1, "hook_sdk": 1, "hook_subprocess": 1},
  "false_negatives": [],
  "ok": true,
  "total_agents": 2
}
```

`ebpf_wire` detects both; the hook surfaces detect only the well-behaved PR bot
(1/2) -- the ghost is the hook blind spot. `false_negatives` lists any agent seen
nowhere (the thesis failure); a non-empty list exits 1.

This gate runs inside `make recette` (it is a dep of the `recette` target): a
simulated agent that RailNode would see on NO surface turns the whole recette
RED, in CI, automatically -- never something to catch by hand.

## The red gate -- the `vanished` negative subject

`corpus/surface/_negative/vanished` is a committed NEGATIVE subject: an agent
that produced nothing observable (empty `proxy_traces` AND empty `wire_flows`),
so it is detected on NO surface. Its ground-truth is `detected_anywhere: false`.

It lives under `_negative/` so the green `recette surface` run does NOT score it
(the loader `load_surface_subjects` skips `_`-prefixed dirs). It is loaded
separately by `load_surface_negatives()` and exercised by
`tests/test_surface_negative.py`, which asserts the scorecard turns RED on it
(`ok == false`, `false_negatives == ("vanished",)`). This proves the thesis gate
fires from a committed corpus subject, not just a unit-test literal.

## Wiring the real RailNode

The reference oracle (`ReferenceSurfaceDiscoveryAdapter`) is the template. A real
RailNode plugs in by implementing the `SurfaceDiscoveryAdapter` protocol
(`recette/surface/detect.py`) -- given a `SurfaceObservation`, return a
`DiscoveryResult`.

`recette/surface/http_adapter.py::HttpSurfaceDiscoveryAdapter` is the ready HTTP
implementation (mirrors `recette/http_adapter.py`): it POSTs each observation
(`{surface, visible}`) to the RailNode detection route (`/v1/detect`, ASSUMED
pending the RailNode API), unwraps a `{success, data}` envelope, and returns a
`DiscoveryResult`. Config (R5/R8): base URL from `INSPECT_IA_AGENTS_RAILNODE_URL`
(default `http://127.0.0.1:8085`), bearer token from `INSPECT_IA_AGENTS_RAILNODE_TOKEN`,
tenant from `INSPECT_IA_AGENTS_TENANT`. httpx is imported lazily with a
zero-dependency stdlib fallback, so the package needs no network to import.

## Gates

```
.venv/bin/python -m unittest discover -s tests
make recette        # includes the `surface` detection gate
.venv-pyaudit/bin/ruff check recette/ tests/ && .venv-pyaudit/bin/mypy recette/
```

## Related

- `.claude/rules/determinism-replay.md` (I4) -- projection/detection/scorecard pure + replay-tested.
- `docs/runbooks/private-dns.md` -- the lab servers the simulated comms route to.
- `recette/adapters.py` -- the `DiscoveryAdapter` / `IdentificationAdapter` family this extends.
