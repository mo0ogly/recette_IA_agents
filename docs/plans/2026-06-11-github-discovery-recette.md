# GitHub Discovery Recette -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give the inspect_ia_agents developer a tool that publishes ground-truth GitHub
test-agent repositories and validates the Discovery/Enrichment Plane GitHubScanner
(`:8081`) against that ground-truth -- without building the scanner itself.

**Architecture:** We author deterministic test-agent *repositories* (real GitHub
repos whose code + CI/CD + optional `.inspect_ia_agents/manifest.json` form the surface the
GitHubScanner reads). Each repo carries a ground-truth describing what Discovery
must conclude. A Python harness registers each repo as a `discovery_source` on the
Discovery REST API `:8081`, triggers a scan, fetches the resulting `discovery_risks`,
and scores them against ground-truth. Because `canonical_agent_id` and `estimated_risk`
are computed internally (opaque, arch invariant 2), the harness verifies **invariant
properties** (detection, count/dedup, action-pattern coverage, target_system,
relative risk-band ordering, scan determinism, policy presence), never exact opaque
values.

**Tech Stack:** Python 3.11+ (existing `recette/` package), `jsonschema`, `httpx`
(optional, for the live `:8081` adapter), `gh` CLI / PyGithub (optional, for publishing
repos). Discovery target: inspect_ia_agents Discovery Plane REST API on `:8081`
(`discovery_sources`, `scan_runs`, `discovery_risks` per arch doc §7).

---

## Context & scope

- **We build:** the test-agent repo corpus + a recette harness that checks the
  GitHubScanner's output against ground-truth.
- **We do NOT build:** the Discovery service, the GitHubScanner, the RiskPort, or the
  policy bundle pipeline. Those are the developer's tool under test.
- **This plan covers the GitHub surface only.** OpenAPI / Temporal / Manifest(MCP)
  surfaces are out of scope here (separate plans), but the corpus layout and the
  adapter abstraction are designed so they slot in later.
- **Reuse:** the existing `recette/` package (forge, agent, adapters, harness,
  scorecard) and `corpus/` ground-truth model. This plan extends them; it does not
  replace them.

## Authoritative facts (from inspect_ia_agents Technical Architecture v1.0, 2026-06-04)

- Discovery / Enrichment Plane: HTTP `:8081`, axum, "REST API · sources · risks".
- GitHubScanner: source = GitHub repository; mechanism = agent code analysis + CI/CD surface.
- Discovery data model (§7):
  - `discovery_sources(source_id, tenant_id, name, adapter, location, auth JSONB, scan_interval_secs, status)`
  - `discovery_risks(risk_id, source_id, tenant_id, canonical_agent_id, action_pattern, target_system, estimated_risk JSONB, generated_policy TEXT, acknowledged BOOL)`
  - `scan_runs(run_id, source_id, tenant_id, status, risks_found INT)`
- Discovery scan flow (§8): Scheduler -> ScannerRegistry::resolve -> Semaphore(10) +
  timeout(300s) -> Scanner -> SecretPort -> RiskPort::score -> DiscoveryPort::upsert_risk
  (dedup on `canonical_agent_id`).
- Dedup index (migration 010): unique `(tenant_id, canonical_agent_id, action_pattern)`.
- Invariant 2: risk scores computed internally; caller-provided scores never trusted.
- Invariant 7: deterministic decisions -- same input => same output; zero randomness.
- ManifestScanner: "inspect_ia_agents JSON manifest -- native format -- highest precision"
  (so an optional `.inspect_ia_agents/manifest.json` in the repo raises scanner precision).

## The "besoin" (requirements) -- what the recette must verify

Because the scanner's `canonical_agent_id` (fingerprinting.rs) and `estimated_risk`
are OPAQUE, ground-truth asserts invariant-level properties, not exact values:

| # | Requirement | Ground-truth field | How checked |
|---|-------------|--------------------|-------------|
| R1 | Detection: every planted agent is found | `expected.detected` | `risks_found >= expected count` and each agent's action_pattern appears |
| R2 | Count / dedup: N distinct agents -> N canonical ids; re-scan does not duplicate | `expected.agent_count` | distinct `canonical_agent_id` count == expected; rescan keeps count stable |
| R3 | Action coverage: planted actions are mapped | `expected.action_patterns[]` | each expected `action_pattern` present in `discovery_risks` for the source |
| R4 | Target system correct | `expected.target_system` | `discovery_risks.target_system` matches (github) |
| R5 | Relative risk ordering: a deliberately dangerous agent outranks a benign one | `expected.risk_rank` (ordinal) | bands derived from `estimated_risk` JSON are monotonic vs `risk_rank` across the corpus |
| R6 | Policy emitted for risky agents | `expected.policy_generated` | `generated_policy` non-empty when expected |
| R7 | Determinism (invariant 7): two scans of the same repo -> identical risk set | implicit | scan twice, assert identical `discovery_risks` (modulo run ids) |
| R8 | No false positives: a repo with no agent yields no risks | `expected.detected=false` | empty `discovery_risks` for that source |

Negative cases (corpus must include): a repo with no agent at all (R8), and a repo
with an over-permissive CI/CD surface that must score higher (R5).

## Open questions / assumptions (resolve before live wiring)

- **A1 (REST routes):** arch doc gives `:8081` as "REST · sources · risks" but not exact
  paths. ASSUMED routes (to confirm against the Discovery OpenAPI): `POST /v1/sources`,
  `POST /v1/sources/{id}/scan`, `GET /v1/scan-runs/{id}`, `GET /v1/sources/{id}/risks`.
  The adapter isolates these so a path change touches one file.
- **A2 (tenant):** dev mode tenant is an env var (`TenantContext dev = env var`, §9).
  Harness sends `tenant_id` via `INSPECT_IA_AGENTS_TENANT` (header or body per the API).
- **A3 (auth/secrets):** repos are public test repos OR private with a token via
  `SecretPort`/`SourceAuth::SecretRef`. Token from env, never committed (R8/R15).
- **A4 (risk band mapping):** `estimated_risk` is JSONB of unknown exact shape. The
  adapter exposes a `risk_band(estimated_risk)->ordinal` extractor, defaulted to read a
  numeric/level field, overridable when the real shape is known.

If A1/A4 cannot be confirmed yet, the live `HttpDiscoveryAdapter` ships behind the
existing pluggable `DiscoveryAdapter` protocol and the corpus is exercised by the
offline `ReferenceDiscoveryAdapter` so the recette is green and ready to flip.

---

## Phase 0: Branch + corpus model extension

### Task 0.1: Create the feature branch

**Step 1:** `git checkout -b feat/github-discovery-recette`
**Step 2:** Confirm clean tree: `git status -s` (the parallel `cmd/python_recette/` WIP
may be present -- do NOT stage it).

### Task 1: Discovery ground-truth schema

**Files:**
- Create: `corpus/schemas/discovery-ground-truth.schema.json`
- Test: `tests/test_discovery_schema.py`

**Step 1: Write the failing test**

```python
import json, unittest
from pathlib import Path
import jsonschema

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "corpus" / "schemas" / "discovery-ground-truth.schema.json"

class TestDiscoverySchema(unittest.TestCase):
    def test_schema_is_valid_and_accepts_minimal_doc(self):
        schema = json.loads(SCHEMA.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        doc = {
            "agent_repo": "gh-pr-bot",
            "target_system": "github",
            "detected": True,
            "agent_count": 1,
            "action_patterns": ["open_pr"],
            "risk_rank": 2,
            "policy_generated": True,
        }
        jsonschema.Draft202012Validator(schema).validate(doc)
```

**Step 2: Run, expect FAIL** -- `python3 -m unittest tests.test_discovery_schema -v` (file/schema missing).

**Step 3: Write the schema** -- fields: `agent_repo` (slug), `target_system`
(enum github/gitlab), `detected` (bool), `agent_count` (int >=0), `action_patterns`
(array of the canonical action vocabulary), `risk_rank` (int ordinal for R5),
`policy_generated` (bool), optional `notes`. `additionalProperties:false`,
required = [agent_repo, target_system, detected].

**Step 4: Run, expect PASS.**

**Step 5: Commit** -- `git add corpus/schemas/discovery-ground-truth.schema.json tests/test_discovery_schema.py && git commit -m "feat(recette): discovery ground-truth schema (invariant-property based)"`

### Task 2: Repo-template structure for a GitHub test agent

**Files:**
- Create: `corpus/repos/README.md` (documents the layout)
- Create: `corpus/repos/gh-pr-bot/repo/` (a real publishable repo tree)
  - `corpus/repos/gh-pr-bot/repo/.inspect_ia_agents/manifest.json` (ManifestScanner native surface)
  - `corpus/repos/gh-pr-bot/repo/.github/workflows/agent.yml` (CI/CD surface)
  - `corpus/repos/gh-pr-bot/repo/agent/main.py` (agent code surface, the action_pattern source)
  - `corpus/repos/gh-pr-bot/repo/README.md`
- Create: `corpus/repos/gh-pr-bot/discovery-ground-truth.json`
- Test: `tests/test_repo_corpus.py`

**Step 1: Write the failing test** -- assert every `corpus/repos/*/` dir has a `repo/`
subtree and a schema-valid `discovery-ground-truth.json`, and that `agent_repo` matches
the directory name.

**Step 2: Run, expect FAIL.**

**Step 3: Author `gh-pr-bot`** -- a benign PR bot:
- `agent/main.py`: opens PRs via the GitHub API (the `open_pr` action_pattern surface).
- `.github/workflows/agent.yml`: scheduled CI that runs the agent (CI/CD surface).
- `.inspect_ia_agents/manifest.json`: declares `canonical` name, capability `open_pr` on `acme/*`.
- `discovery-ground-truth.json`: `{detected:true, agent_count:1, action_patterns:["open_pr"], target_system:"github", risk_rank:2, policy_generated:true}`.

**Step 4: Run, expect PASS.**

**Step 5: Commit.**

### Task 3: Two more repos for relative ranking + a true negative

**Files:**
- Create: `corpus/repos/gh-readonly-reporter/` (risk_rank 1, read-only, action `read_repo`)
- Create: `corpus/repos/gh-admin-overreach/` (risk_rank 3, `manage_webhook`+`push`, broad CI perms)
- Create: `corpus/repos/gh-no-agent/` (a plain library repo, `detected:false`, R8)
- Each with `repo/` subtree + `discovery-ground-truth.json`.

**Step 1-5:** same TDD loop; `test_repo_corpus.py` parametrizes over all repos.
Assert risk_rank is strictly ordered across reporter(1) < pr-bot(2) < admin-overreach(3),
and `gh-no-agent` has `detected:false, agent_count:0, action_patterns:[]`.

**Commit** after the suite is green.

---

## Phase 1: Discovery adapter (pluggable, live + reference)

### Task 4: Extend the DiscoveryAdapter contract for source-based scanning

**Files:**
- Modify: `recette/adapters.py` (add a richer `DiscoveryRisk` dataclass + a
  `SourceScanAdapter` protocol: `register(location)->source_id`,
  `scan(source_id)->run_id`, `await_run(run_id)->status`, `risks(source_id)->list[DiscoveryRisk]`)
- Test: `tests/test_source_scan_adapter.py`

`DiscoveryRisk` mirrors `discovery_risks`: `canonical_agent_id, action_pattern,
target_system, estimated_risk(dict), generated_policy(str|None)`.

**Step 1: failing test** with a fake in-memory `SourceScanAdapter` that returns a known
risk set for a known location; assert the dataclass + protocol shape.
**Steps 2-4:** implement, green.
**Step 5: commit.**

### Task 5: ReferenceSourceScanAdapter (offline, reads the repo tree)

**Files:**
- Modify: `recette/adapters.py` (add `ReferenceSourceScanAdapter` that, given a
  `corpus/repos/<slug>/repo/` path, derives the same risk set the GitHubScanner should:
  parse `.inspect_ia_agents/manifest.json` + `.github/workflows` + `agent/` for action patterns;
  emit a deterministic `canonical_agent_id = sha256(slug+action_pattern)[:16]`; assign a
  reference `estimated_risk = {"level": risk_rank}`; `generated_policy` non-empty when
  risk_rank>=2).
- Test: `tests/test_reference_scan.py`

This is the offline oracle: it lets the whole recette run green WITHOUT the real
Discovery service, and documents exactly what a correct scanner must produce.

**Steps:** TDD loop; assert determinism (two calls byte-identical, invariant 7) and
that it reproduces each repo's ground-truth. **Commit.**

### Task 6: HttpDiscoveryAdapter for the live :8081 REST API

**Files:**
- Create: `recette/http_adapter.py` (`HttpSourceScanAdapter` implementing
  `SourceScanAdapter` against `:8081`; uses the ASSUMED routes from A1; `httpx` optional
  import with a clear error if absent; tenant via `INSPECT_IA_AGENTS_TENANT`; token via env)
- Test: `tests/test_http_adapter.py` (uses a stub transport / monkeypatched client --
  NO real network in tests)

**Step 1: failing test** -- with a fake transport returning canned `:8081` JSON, assert
`register/scan/await_run/risks` parse into `DiscoveryRisk` objects and unwrap the
response envelope explicitly.
**Steps 2-4:** implement against the assumed routes, isolate every path in one module.
**Step 5: commit** with a note that A1 routes are assumed pending the Discovery OpenAPI.

---

## Phase 2: Discovery recette harness + scorecard

### Task 7: Discovery scorecard (invariant-property scoring)

**Files:**
- Create: `recette/discovery_scorecard.py`
- Test: `tests/test_discovery_scorecard.py`

Scores R1-R8 per repo and aggregates: detection rate, action-pattern coverage,
target accuracy, risk-ordering correctness (Kendall-style monotonic check across the
corpus), determinism pass, false-positive count, false-negative count.

**Steps:** TDD; include a NEGATIVE test -- a tool that returns no risks must surface as
N false negatives and a 0% detection rate. **Commit.**

### Task 8: Discovery harness wiring

**Files:**
- Create: `recette/discovery_harness.py` (`run_discovery_recette(adapter)`:
  iterate `corpus/repos/*`, register+scan+fetch via the adapter, compare to
  `discovery-ground-truth.json`, build the scorecard; run the risk-ordering check across
  the full set; run each repo twice for the determinism check R7)
- Modify: `recette/__main__.py` (add `discovery` subcommand:
  `python -m recette discovery --adapter reference|http`)
- Test: `tests/test_discovery_harness.py`

**Step 1: failing test** -- `run_discovery_recette(ReferenceSourceScanAdapter())` returns
an all-pass scorecard over the repo corpus.
**Steps 2-4:** implement, green.
**Step 5: commit.**

### Task 9: CLI smoke + docs

**Files:**
- Modify: `corpus/README.md` and `.claude/rules/recette-corpus.md` (document the repo
  corpus + discovery recette + `python -m recette discovery`)
- Run: `python3 -m recette discovery --adapter reference` -> scorecard PASS, exit 0.

**Commit.**

---

## Phase 3: Publisher to real GitHub (developer-facing tool)

> This is the piece that turns `corpus/repos/*/repo/` trees into the real repos the
> developer points their GitHubScanner at. Side-effecting (creates remote repos) --
> gated and explicit.

### Task 10: Repo publisher

**Files:**
- Create: `recette/publish.py` (`publish_repo(slug, owner, visibility="private",
  dry_run=True)`: init a git repo from `corpus/repos/<slug>/repo/`, create the GitHub
  repo via `gh` CLI or PyGithub, push; `dry_run` by default prints the plan and does
  nothing)
- Modify: `recette/__main__.py` (`python -m recette publish <slug> --owner <o> [--apply]`)
- Test: `tests/test_publish.py` (dry-run only; assert it computes the right repo name,
  files, and remote URL WITHOUT touching the network)

**Constraints:**
- `--apply` (real creation) requires an explicit flag; default is dry-run.
- Token from env (`GH_TOKEN` / gh auth), never committed.
- Never force-push; never touch a repo it did not create (check existence first).

**Steps:** TDD the dry-run logic; the `--apply` path is exercised manually by the dev.
**Commit.**

### Task 11: End-to-end manual recette (developer runbook)

**Files:**
- Create: `docs/runbooks/github-discovery-recette.md`

Document the full loop the developer runs:
1. `python -m recette publish gh-pr-bot --owner <test-org> --apply` (and the others)
2. Register sources + scan via the developer's Discovery `:8081` (or
   `python -m recette discovery --adapter http`)
3. Read the scorecard; investigate any MISS against `discovery-ground-truth.json`.
4. Aggregate: detection rate, action coverage, risk ordering, determinism, FP/FN.

No code; this is the handoff artifact. **Commit.**

---

## Definition of done

- `python3 -m unittest discover -s tests` green (existing 12 + new discovery tests).
- `python3 -m recette validate` green (manifests + scenarios + ground-truths + repos).
- `python3 -m recette discovery --adapter reference` -> scorecard PASS, exit 0.
- `corpus/repos/` holds >= 4 GitHub repos: ranked benign/medium/dangerous + one true
  negative, each with a publishable `repo/` tree and schema-valid ground-truth.
- `HttpSourceScanAdapter` implemented behind the pluggable protocol, unit-tested with a
  stubbed transport, ready to flip once A1 (routes) + A4 (risk shape) are confirmed.
- Publisher dry-run tested; `--apply` documented in the runbook.
- No secrets committed; no real network in the test suite; determinism (invariant 7)
  asserted for both the reference scanner and the rescan check (R7).

## What this plan deliberately does NOT do

- Does not implement the GitHubScanner, RiskPort, or policy bundle pipeline.
- Does not verify the Ed25519 bundle signature chain (that is the Control Plane recette,
  a later plan once the bundle format is pinned).
- Does not cover OpenAPI / Temporal / Manifest(MCP) surfaces (separate plans; the
  `SourceScanAdapter` + repo-corpus abstractions are built to extend to them).
