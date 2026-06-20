# Agent registry + catalog -- runbook

> Two read-only registries describe the system's agent population. The
> **generated registry** (`GET /registry/agents`) is a DERIVED projection of the
> corpus manifests -- never written by hand -- one row per subject. The
> **declarative catalog** (`GET /catalog/summary`) reads a published registry
> file and exposes only INVARIANT discovery properties from it (counts,
> distinct names, tool coverage, tag union), with a native Rust engine in
> cross-agreement.
>
> Python code: `recette/registry.py` (pure), `recette/api/routers/registry.py`,
> `recette/api/routers/catalog_registry.py`, `recette/catalog_sync.py`.
> Rust engine: `discoveryprobe/discoveryprobe-catalog/`.
> Console: `console/src/pages/agent-registry/` and `console/src/pages/registry/`.

## Why this subsystem exists

The recette must be able to present, without side effects or opaque
recomputation, "who the agents are" from two complementary angles:

1. **Generated registry** -- an aggregate of ALL the corpus subjects (git agents
   + MAF subjects), built on demand from the manifests. This is the
   auto-registry-on-merge concept (microsoft/discovery style): the registry is a
   function of the manifests, never a hand-maintained file that could drift.
2. **Declarative catalog** -- the machine-readable index that a discovery source
   publishes (`version` + `entries`). The catalog shows only invariants (R20:
   discovery ground-truth is invariant-only, never an exact score), so it can
   serve as a test bench for external discovery tools.

Both are **read-only** on the API side and on the console side.

## Generated registry -- what it does

### Construction (derived, pure)

`recette/api/routers/registry.py::build_agent_registry()` scans two families of
subject directories and produces one row per manifest:

- `discover_agent_dirs()` (`recette/harness.py`) -> each `manifest.json` of a git
  agent, family `"git"`.
- `discover_maf_dirs()` (`recette/maf_harness.py`) -> each `spec.json` of a MAF
  subject, family `"maf"`.

Each row is produced by the pure function `registry_row(manifest, family)`
(`recette/registry.py`). A row carries exactly these fields:

| Field | Source in the manifest | Behavior if absent |
|-------|------------------------|--------------------|
| `agent_id` | `agent_id` | `None` |
| `name` | `name` | `None` |
| `kind` | `kind` | default `"git_agent"` |
| `family` | (parameter `git` / `maf`) | -- |
| `version` | `version` | `None` |
| `target_systems` | `target_systems` | `[]` |
| `capabilities` | `len(capability_scope)` | `0` |
| `standard` | `source.standard` | `None` |
| `publisher` | `metadata.publisher.name` | `None` |
| `compliance` | `metadata.compliance` | `[]` |
| `party` | `metadata.party` | `None` |
| `tags` | `metadata.tags` | `[]` |

Optional metadata fields are surfaced as `None` / `[]` when absent --
**never invented** (R4). Rows are sorted by `agent_id`.

### Endpoint output

`GET /registry/agents` returns:

```json
{ "generated": true, "count": <int>, "agents": [ <registry_row>, ... ] }
```

### Console page

Route `/agent-registry` (navigation label **Registry**),
`console/src/pages/agent-registry/index.tsx`, via `getAgentRegistry()`
(`console/src/api/client.ts`, `GET /registry/agents`). The page displays a table
(`agent`, `kind`, `version`, `party`, `compliance`, `publisher`, `tags`) with a
**Party** filter (`all` / `1p` / `3p`). Help: topic `agent_registry`
(`console/src/components/help/helpTopics.tsx`).

## Declarative catalog -- what it does

### Source and invariant projection

`recette/api/routers/catalog_registry.py` reads a local JSON registry file
(default `corpus/catalog/agent-registry.json`, overridable via
`INSPECT_IA_AGENTS_CATALOG_REGISTRY`) and PROJECTS it via `_project()` onto a
strictly invariant view:

```json
{
  "version": "<str>",
  "summary": { "total": <int>, "unique": <int>, "with_tools": <int>, "tags": [<str>...] },
  "agents": [ { "name", "version", "publisher_name", "description", "tags", "tool_count" } ]
}
```

- `total` = number of entries, `unique` = distinct names, `with_tools` = entries
  where `len(associated_tools) + len(foundry_tools) > 0`, `tags` = sorted and
  deduplicated union.
- The projection is a **pure function** of the JSON (sorted + deduplicated tags,
  agents in registry order): same registry -> byte-stable summary (I4). The
  `generated_at` field is operational metadata and never enters the projection.
- No opaque value is exposed (R20).

Endpoint: `GET /catalog/summary`.

### Native Rust engine and cross-agreement

`GET /catalog/rust-summary` runs the compiled binary
`discoveryprobe/target/release/discoveryprobe-catalog` (overridable via
`INSPECT_IA_AGENTS_CATALOG_RUST_BIN`) on the same registry file, without a shell,
with fixed arguments taken from the configuration -- never a request input
(`subprocess.run([str(binary), str(registry)], timeout=10)`). Output:

```json
{ "available": <bool>, "engine": "discoveryprobe-catalog (Rust)",
  "summary": {...}?, "reason": "<str>"?, "agreement": <bool>?, "python_summary": {...}? }
```

`agreement` is `true` iff the Rust invariant summary equals the Python
projection: this is the cross-agreement guarantee between the two engines (the
Rust `DiscoverySummary` and the Python projection share the same invariants).

The binary is built with `cargo build --release -p discoveryprobe-catalog`; on
the CLI it is used as `discoveryprobe-catalog <registry.json>` (prints the
invariant summary).

### Console page

Route `/registry` (navigation label **Catalogue**),
`console/src/pages/registry/index.tsx`, via `getCatalogSummary()` and
`getCatalogRustSummary()`. The page displays the counters (Agents / Unique /
With tools / Tags), the tag union, one card per agent
(`RegistryAgentCard.tsx`, an agent with no tool is shown distinctly, never
hidden) and a Rust engine panel with an indicator `Rust == Python agreement` /
`Rust/Python DISAGREEMENT`, or `binary not compiled` if the engine is absent.

## Refresh the catalog (the only network operation)

The catalog API reads a LOCAL file to stay deterministic and offline
(I4 / R20). Synchronization is an explicit, operator-driven step, provided by
`recette/catalog_sync.py`:

```
python -m recette.catalog_sync
```

- Source: `INSPECT_IA_AGENTS_CATALOG_REGISTRY_URL` (allowed schemes:
  `http`, `https`, `file`). Never a hardcoded URL (R5). A `file://` makes the
  sync exercisable without a network.
- Destination: `INSPECT_IA_AGENTS_CATALOG_REGISTRY` or by default
  `corpus/catalog/agent-registry.json`.
- The source must be a JSON object carrying an `entries` array, otherwise the
  local file is left intact and `CatalogSyncError` is raised.

## Flow

```mermaid
flowchart TD
  subgraph Registre_genere
    M1["Corpus manifests<br/>(git agents + MAF subjects)"] -->|discover_agent_dirs / discover_maf_dirs| RB["build_agent_registry()<br/>registry_row (pure)"]
    RB --> RA["GET /registry/agents<br/>{generated, count, agents}"]
    RA --> UI1["Console /agent-registry<br/>(label Registry)"]
  end
  subgraph Catalogue_declaratif
    SRC["Remote source<br/>(http/https/file)"] -->|python -m recette.catalog_sync| FILE["corpus/catalog/agent-registry.json<br/>(local file)"]
    FILE -->|_project (pure)| CS["GET /catalog/summary<br/>invariant summary"]
    FILE -->|discoveryprobe-catalog| CR["GET /catalog/rust-summary<br/>+ cross-agreement"]
    CS --> UI2["Console /registry<br/>(label Catalogue)"]
    CR --> UI2
  end
```

## Fail-safe behaviors

- **Catalog absent / unreadable / malformed**: `_load_catalog()` returns an
  EMPTY catalog (`version ""`, zeroed summary, agents `[]`) with a logged
  warning -- never a 500.
- **Rust engine not compiled / errored / timed out / non-JSON output**:
  `GET /catalog/rust-summary` returns `available: false` with a `reason` --
  never a 500, never a fabricated result. The page leaves the Rust panel in an
  unavailable state.
- **Invalid sync** (missing source, unsupported scheme, unreachable source,
  non-conforming payload): `CatalogSyncError` is raised and logged; the good
  local file is never overwritten by a partial or corrupted registry.
- **Missing registry metadata**: surfaced as `None` / `[]` (generated registry)
  or an empty field (`—` on the UI side) -- never invented.

## Invariants

- **I1 (immutability)** -- both registries are read-only; no UPDATE/DELETE is
  involved. The generated registry is a derived projection, reconstructible from
  the manifests (disposable).
- **I4 (deterministic replay)** -- `registry_row` and `_project` are pure
  functions (sort by `agent_id`, sorted + deduplicated tags): same input ->
  byte-stable output. The Rust engine computes the same invariants
  (cross-agreement). The only network operation (sync) is out of the request
  path.
- **R20 (invariant ground-truth)** -- the catalog exposes only invariant
  properties (counts, distinct names, tool coverage, tag union), never an opaque
  value nor an exact score.

## Quick checks

```
curl -s http://127.0.0.1:8090/registry/agents | head
curl -s http://127.0.0.1:8090/catalog/summary | head
curl -s http://127.0.0.1:8090/catalog/rust-summary | head
```

The API is launched via `./recette.sh platform up` (canonical port 8090, R19).
Reference tests: `tests/test_api_registry.py`, `tests/test_api_catalog_summary.py`,
`tests/test_api_catalog_rust.py`, `tests/test_catalog_sync.py`.

## See also

- `docs/runbooks/github-discovery-recette.md` -- the discovery recette.
- `.claude/rules/recette-corpus.md` -- the three forms of an agent, discovery vs
  identification, invariant ground-truth.
- `.claude/rules/maf-standard.md` -- the MAF subjects aggregated in the generated registry.
