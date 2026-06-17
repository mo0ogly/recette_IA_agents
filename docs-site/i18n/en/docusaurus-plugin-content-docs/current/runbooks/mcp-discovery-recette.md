# MCP discovery recette -- runbook

The `mcp` discovery surface validates that the Manifest/MCP scanner detects an agent
described by an MCP server manifest and scores it on the same invariant properties as
the github surface (detection, count/dedup, action coverage, target, relative risk
ordering, policy presence) -- never opaque scores (I4 determinism).

## Corpus

```
corpus/manifests/<slug>/
  discovery-ground-truth.json   # invariant expectations (schema: discovery-ground-truth)
  repo/
    .inspect_ia_agents/manifest.json    # inspect_ia_agents manifest with target_system: "mcp"  (detected agent)
    mcp.json                    # plain MCP server descriptor (true-negative decoy)
```

A subject is detected when `repo/.inspect_ia_agents/manifest.json` declares an agent with
`target_system: "mcp"` and git-canonical capabilities (e.g. `read_repo`, `open_pr`).
A plain `mcp.json` with arithmetic tools and no inspect_ia_agents manifest is a TRUE NEGATIVE:
the scanner must not flag it (false-positive guard, see `mcp-no-agent`).

Existing subjects: `mcp-pr-bot`, `mcp-readonly-reporter`, `mcp-admin-overreach`
(detected) and `mcp-no-agent` (true negative).

## Run

```
python3 -m recette validate                       # schema-validate every corpus incl mcp
python3 -m recette discovery --surface mcp        # mcp surface scorecard (offline oracle)
python3 -m recette discovery --adapter http       # against a live scanner on :8081
python3 -m recette report                         # unified verdict: identification + MAF + every surface
```

The surface is registered in `recette/discovery_harness.py`:
`SURFACE_ORDER` includes `"mcp"`, mapped to `corpus/manifests/` by `SURFACE_CORPUS`.
The reference scanner (`ReferenceSourceScanAdapter._from_manifest`) reads the
`.inspect_ia_agents/manifest.json` directly.

## API

The aggregate scorecard exposes every surface, mcp included:

```
GET /subjects/scorecard
-> { "identification": {...}, "maf": {...},
     "discovery": { "github": {...}, ..., "mcp": {repos, passed, false_positives,
        false_negatives, ordering_ok, all_passed} },
     "all_passed": bool }
```

`GET /subjects` lists the unified corpus subjects (git_agent + maf_agent families).

## Console

The `Discovery` page (`console/src/pages/discovery/`) renders `GET /subjects/scorecard`:
one row per discovery surface (github/gitlab/temporal/openapi/mcp) plus the
identification and MAF summaries, with the aggregate PASS/FAIL verdict. It asserts
invariant properties only. Contract test + captured fixture:
`console/src/pages/discovery/index.test.tsx` + `__fixtures__/scorecard.fixture.json`.

## Extending

Add a detected subject: create `corpus/manifests/<slug>/repo/.inspect_ia_agents/manifest.json`
with `target_system: "mcp"` and its capabilities, plus a `discovery-ground-truth.json`
asserting detection, `agent_count`, `action_patterns`, `risk_rank` and `policy_generated`.
Keep `risk_rank` monotonic with risk so the cross-corpus ordering check stays green.
