# R27 Docker Runtime Mandatory -- the platform RUNS in Docker, bare-host is a dev crutch

> The governed platform (API :8090 + lab mock :8082) is a Dockerized service.
> Running it as bare-host Python processes (`./recette.sh platform up`,
> `cicd/api.sh start`) is a DEV convenience ONLY. It is NEVER the basis for a
> "done", "it works", "live proof", or "recette passed" claim. Any live proof,
> smoke, or demonstration of the running platform MUST execute against the
> containerized services, or it does not count.

## Why this rule exists

Incident 2026-07-06: the whole passport-admission live proof (R14) was executed
against BARE-HOST processes -- `bash cicd/api.sh start`, cgroup NOT docker. The
operator caught it: "on est bien en docker ? ... inadmissible cette derive." The
app is designed to run in Docker (`Dockerfile`, `docker-compose.yml` with a real
`api` service `python -m recette.api` on :8090, `lab-mock`, `platform-init`,
`gates`, `tests`, `e2e`), yet the drift was to prove everything on the host. A
bare-host proof does NOT exercise the image the deployment actually ships (R22
docker-dependency-adequation): a missing dep, a wrong extra, a path that only
resolves on the host is invisible until it fails in the container. So a host
proof is a FALSE proof (R14 cousin).

## The rule (BLOCKING)

1. **The platform runs in Docker.** The authoritative runtime is the compose
   `api` service (+ `lab-mock`, `platform-init`), built from the repo `Dockerfile`.
   Bring it up with the docker path, never a hand-launched or `recette.sh
   platform up` bare-host python:
   ```
   docker compose up -d api
   docker compose ps
   docker compose logs -f api
   ```
   (`api` `depends_on` `lab-mock` healthy + `platform-init` completed, so
   `up -d api` brings the whole governed stack. Port `${API_HOST_PORT:-8090}:8090`.)
   Verified 2026-07-06 in `docker-compose.yml` (service `api`) and
   `cicd/lib/common.sh::dc` (`docker compose` wrapper from the repo root).

2. **A live proof / smoke / "done" claim about the RUNNING platform MUST be in
   the container.** Before writing "live proof", "smoke pass", "it works",
   "deployed", or "recette passed" about the platform, confirm the process under
   test is containerized -- `cat /proc/<pid>/cgroup | grep docker`, or
   `docker compose ps` shows it Up, or the request hit the mapped container port.
   A bare-host `API-BARE-HOST` cgroup is NOT a valid proof surface. If you must
   prove on the host for a quick dev check, say so EXPLICITLY ("preuve bare-host,
   non-Docker") -- never let it read as a Docker/production proof (R13/R14).

3. **Bare-host is dev-only, and scoped.** `./recette.sh platform up` /
   `cicd/api.sh start` stay available for a fast inner-loop unit/dev check, but:
   - they are NOT the runtime of record;
   - they NEVER back a delivery claim;
   - the moment behavior is being validated for real (recette, smoke, demo,
     handover), it moves into the container.

4. **Docker dependency adequation is enforced here (R22).** A new runtime dep
   (e.g. an optional extra the admission/passport path needs) MUST be installed
   by the image (`Dockerfile` `pip install -e ".[...]"`) in the SAME change, and
   proven by a containerized run -- not by a host venv that happens to have it.

## Known gap to close (follow-up, tracked)

`./recette.sh` exposes `up|down` for the docker LAB (`cicd/docker.sh`, only
`discovery-mock`) and `platform up` for the BARE-HOST governed stack, but NO
single recette.sh command brings the governed `api` service up in Docker. Until
that is wired (a `recette.sh platform up --docker` or equivalent driving
`docker compose up -d api`), use `docker compose up -d api` directly. Wiring it
into recette.sh keeps R19 (single entry point) AND R27 (docker runtime) both
true; do it before relying on the bare-host path again.

## Quick check before claiming a platform proof

```
docker compose ps                       # api service Up (healthy)?
APIPID=$(cat .run/api.pid 2>/dev/null); cat /proc/$APIPID/cgroup | grep -q docker \
  && echo "containerized" || echo "BARE-HOST -- not a Docker proof"
```

## Related

- `.claude/rules/docker-dependency-adequation.md` (R22) -- deps must match the image.
- `.claude/rules/recette-sh-single-entrypoint.md` (R19) -- one launcher; reconcile:
  recette.sh must drive the DOCKER lifecycle for the governed platform, not bare-host.
- `.claude/rules/no-fix-without-live-verification.md` (R14) -- a proof on the wrong
  surface (host, not container) is not a proof.
