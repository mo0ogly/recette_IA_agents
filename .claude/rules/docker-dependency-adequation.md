# R22 Docker Dependency Adequation -- installs, requirements, Dockerfile, pyproject MUST agree

> This app runs in **Docker**. Every dependency story MUST be consistent across
> the four places that declare it: `pyproject.toml` (deps + extras), the
> `Dockerfile` (`pip install -e ".[...]"`), any `requirements*.txt`, and the
> environment you VERIFY a feature in. An install that lives only in a throwaway
> side-venv -- diverging from what the container actually builds -- is an
> "adequation" violation: it proves nothing about the running app.

## Why this rule exists

2026-06-15: the optional PyRIT attacker (`[redteam]` extra) was verified by
`pip install`-ing pyrit into a disposable `.venv-pyrit`. That side-venv pulled
**939 MB** (azure-*, openai, transformers, datasets, pandas, scipy, numpy; 52 ->
116 packages) -- nothing the base Docker image carries. The operator flagged it:
under Docker, what I install must be **en adequation** with the container's
declared requirements, not a parallel reality. Verifying in an env that does not
match the image is a false proof (R13/R14 cousin).

## The rule (BLOCKING for any dependency change)

1. **Single source of truth = `pyproject.toml`.** Base `dependencies` stays
   minimal (today: `jsonschema` only). Everything else is an explicit OPTIONAL
   extra (`real`, `temporal`, `bundle`, `maf`, `api`, `postgres`, `nats`,
   `redteam`). Never add a hard dependency for an optional feature (R20).

2. **The Dockerfile install list is intentional and must match the app's needs.**
   The image builds `pip install -e ".[bundle,api]"` (+ `jsonschema`). If a
   feature the running container must serve needs a new extra, ADD that extra to
   the Dockerfile line in the SAME change -- do not let code rely on a dep the
   image does not install. Conversely, do NOT bake a heavy optional extra into the
   base image just because you installed it locally.

3. **Heavy optional extras stay opt-in and OUT of the base image -- documented.**
   `[redteam]` (pyrit, ~939 MB) is NOT in the Dockerfile by design (R20): the
   redteam CORE (native attacker, deterministic gate, recorder, promote, /sim API)
   runs on `[bundle,api]`+jsonschema with NO pyrit. PyRIT is import-guarded and
   only needed for `recette redteam-record --attacker pyrit`. To use it in the
   container: `pip install -e ".[redteam]"` (documented in the runbook), or a
   dedicated build stage/ARG -- never silently bloat the lean base image.

4. **Pin the extra to the version whose API you verified.** Code written against
   a specific API MUST pin a floor at that version. `pyrit>=0.5` was wrong: the
   code uses the 0.14 `TextJailBreak` API; an old 0.5.x would install and break.
   Fixed to `pyrit>=0.14`. A loose floor that admits an incompatible API is an
   adequation violation.

5. **Verify a feature in an env that matches the container.** A side-venv is fine
   to PROVE an optional extra works (Docker is disposable, installs OK --
   [[docker-disposable-env-installs-ok]]), but the dependency declaration
   (pyproject extra + pin + Dockerfile/runbook) MUST be updated so the proof is
   reproducible from the declared requirements, not just from your local venv.

## Quick check before declaring a dependency change done

```
grep -n "dependencies\|optional-dependencies" pyproject.toml   # source of truth
grep -n "pip install" Dockerfile                                # what the image builds
# new feature needs extra X at runtime in the container? -> X is in the Dockerfile line.
# optional/heavy extra? -> NOT in base image, pinned to the verified version, documented.
```

## Related

- `.claude/rules/recette-and-test-constraints.md` (R20) -- zero hard dep beyond
  jsonschema; optional SDKs are extras.
- `.claude/rules/vuln-fix-latest-version.md` (R17) -- pin/upgrade deliberately.
- `.claude/rules/no-fix-without-live-verification.md` (R14) -- verify for real, in
  a representative env.
- memory `docker-disposable-env-installs-ok` -- installs into gitignored venvs are
  authorized here; this rule adds: keep them in adequation with the declared reqs.
