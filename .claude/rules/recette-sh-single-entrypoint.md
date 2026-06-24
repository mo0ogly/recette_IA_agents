# R19 recette.sh -- single entry point, never hand-launch services or change ports

## Why this rule exists

Incident 2026-06-14: to screenshot the console I hand-launched a second vite
on a random port (`--port 5191`), restarted the API manually with an ad-hoc
`INSPECT_IA_AGENTS_CORS_ORIGINS`, and started a raw `.venv/bin/python -m recette.api`
on 8090. That manual API squatted the canonical port, so the operator's
`./recette.sh platform up` could not bind 8090 and silently fell back to
**8100** (port-search in `cicd/platform.sh`). The console (started by the
script with `VITE_INSPECT_IA_AGENTS_API_URL` pinned to the API port) and the API ended
up on mismatched ports. The operator had to stop me: the project already has
ONE launcher that wires every port and env var correctly.

## The single entry point

`./recette.sh` (delegates to `cicd/*.sh`) owns the whole lifecycle. Ports and
hosts are defined ONCE in `cicd/lib/common.sh` and must not be overridden:

| Service | Canonical | Env override (DO NOT set by hand) |
|---------|-----------|-----------------------------------|
| API (governed) | `127.0.0.1:8090` | `INSPECT_IA_AGENTS_API_PORT` / `INSPECT_IA_AGENTS_API_HOST` |
| Lab mock | `:8082` | `INSPECT_IA_AGENTS_LAB_PORT` |
| Console (vite) | `localhost:5173` | `INSPECT_IA_AGENTS_CONSOLE_PORT` |

The console is launched by `cicd/platform.sh console start`, which exports
`VITE_INSPECT_IA_AGENTS_API_URL="http://${API_HOST}:${API_PORT}"` and `--strictPort`,
so the UX is wired to the live API automatically. State (pids/ports) lives in
`.run/` (`api.pid`, `api.port`, `console.pid`, `lab.pid`). Launching a service
outside the script leaves `.run/` inconsistent and breaks `status`/`stop`.

## Command surface (interactive menu + CLI -- full parity)

Two ways to drive it, same underlying `cicd/*.sh`:

- **Interactive:** `./recette.sh` (no arg) opens a menu of 10 category
  submenus; each lists its actions and `0` returns to the top. The menu is in
  full parity with the CLI -- every action below is reachable from a submenu.
- **Non-interactive:** `./recette.sh <cmd> [args]` for scripts/CI.

| Category (submenu) | CLI form | What it does |
|--------------------|----------|--------------|
| Docker lab | `up\|down\|restart\|rebuild\|ps\|logs\|shell` | docker-compose lab lifecycle |
| API governed | `api start\|stop\|restart\|status\|logs` | governed API on :8090 |
| Checks | `test\|gates\|report` (`test --docker`) | unittest, ruff/mypy/bandit, report |
| Git | `git status\|pull\|push\|sync` | repo helpers (R21-aware) |
| Platform + Console | `platform up\|down\|restart\|status\|purge`, `console start\|stop\|status\|logs` | lab mock + API + vite UX |
| Campaigns | `campaign list\|run <name> [--json]` | action campaigns (recursive, see below) |
| Recette & Discovery | `validate`, `run`, `discovery`, `smoke`, `discovery-build`, `probe-ebpf-build`, `probe-grant-caps` | schema-validate, identification scorecard, discovery scorecard, e2e smoke, native Rust + eBPF builds |
| Proxy overlays | `wire up\|down\|status\|logs`, `llm-proxy up\|down\|status\|logs` | optional mitmproxy wire-interception + LiteLLM gateway (Docker) |
| Console & Docs | `console-build\|console-test`, `docs-build\|docs-serve` | React tsc+vite/vitest, Docusaurus fr+en |
| Cleanup | `platform purge` | stop+free local web servers (API/lab/console) |

**Campaigns are discovered recursively.** Campaign files live under
`campaigns/` AND its subgroups (`campaigns/{bnp,coverage,multidomain,rag,role-matrix}/`).
`campaign list`, the menu picker, and `campaign run <name>` all resolve
recursively: list/picker show the group-relative path (`bnp/sec-1-soc-compromise`),
and `run` accepts a bare short name, a `group/name`, a filename, or a path. Do
NOT reintroduce a top-level-only glob/`-maxdepth 1` -- it silently hides the
nested campaigns (regression fixed 2026-06-24).

## The rule (BLOCKING)

1. **Never hand-launch a project service.** No raw `npm run dev`, `npx vite`,
   `python -m recette.api`, or `uvicorn` from the shell. Use the script:
   - `./recette.sh platform up` -- lab mock + governed API
   - `./recette.sh console start` -- console UX (wired to the API)
   - `./recette.sh platform status` -- snapshot before touching anything
   - `./recette.sh api start|stop|restart|status|logs`
   - `./recette.sh platform restart|down|purge`
2. **Never change a port -- the canonical port is enforced, not relocated.**
   Do not pass `--port`, do not export `INSPECT_IA_AGENTS_*_PORT`, do not pick a free
   port to dodge a conflict. If the canonical port is busy, the holder is
   KILLED so the service binds where it is expected. `platform.sh` does this
   automatically (`_kill_port_holder`); relocating to 8091/8100/... is a bug,
   not a feature. Operator policy (2026-06-14): "si un port est pris on le
   kill" -- a port is not a game of musical chairs.
3. **Never set `INSPECT_IA_AGENTS_CORS_ORIGINS`, `VITE_INSPECT_IA_AGENTS_API_URL`, or other
   wiring env vars by hand.** The script sets them from the canonical values.
4. **Inspect before acting.** Run `./recette.sh platform status` (or read
   `.run/*.pid` / `.run/api.port`) first. If a tracked service is already up,
   reuse it -- do not spawn a parallel one.
5. **If you must reach a service for a check** (curl a health route, drive a
   browser), target the canonical port the script published, read from
   `.run/api.port` if unsure. Do not start your own copy.

## Cleanup obligation

If a previous turn left a hand-launched process behind, stop ONLY that process
(verify it is not the one named in `.run/*.pid`), then hand control back to the
script. Never kill a script-tracked pid out from under the operator.

## Quick check before launching anything

```
./recette.sh platform status
cat .run/api.port
ss -tlnp | grep -E ':(8090|8082|5173)'
```

## Related

- `cicd/lib/common.sh` -- the single source for ports/hosts (R5 Config First).
- `.claude/rules/no-fix-without-live-verification.md` (R14) -- when a live
  check is needed, reach the script-managed service, do not stand up your own.
