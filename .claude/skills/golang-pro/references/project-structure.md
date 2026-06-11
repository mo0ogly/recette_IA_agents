# Project Structure -- LIA-SEC Go Layout

Load this reference when deciding where a new package/file goes, touching `go.mod`, or creating an internal package.

## Table of Contents

1. LIA-SEC Go module layout
2. cmd/ vs pkg/ vs internal/
3. The `cmd/sigma_web/` sub-module (R18 critical)
4. build_secure_lia.sh whitelist (R1)
5. Package naming
6. File naming
7. go.mod management
8. Internal packages
9. vendoring status

---

## 1. LIA-SEC Go module layout

```
/opt/lia-sec/dev/                      # Root module: github.com/mo0ogly/sigma_rules_processor
├── go.mod                             # Root go.mod (pkg/* and bin/* live here)
├── go.sum
├── cmd/
│   ├── sigma_web/                     # SUB-MODULE (own go.mod)
│   │   ├── go.mod                     # module sigma_web_backend
│   │   ├── go.sum
│   │   ├── backend_8081.go            # main() + route registration
│   │   ├── build_secure_lia.sh        # Whitelist build script (R1)
│   │   ├── sigma_web_backend          # Binary (48 MB, gitignored)
│   │   ├── migrations/                # PostgreSQL migrations NNN_*.sql
│   │   └── *.go                       # 613 files, 560+ routes
│   ├── lia_recette/                   # CLI validator (root module)
│   ├── lia_admin_pwreset/             # Admin tool (root module)
│   └── ...
├── pkg/
│   ├── engine/                        # LIA-Scan rule engine (root module)
│   ├── model/                         # Domain types (rules, modifiers)
│   ├── validator/                     # 3 validators (recipe, reportrule, ultimate)
│   ├── compliance/                    # Compliance engine
│   ├── utils/                         # Shared utilities (yamlconv)
│   └── ...
├── bin/
│   └── lia_scan_engine                # Compiled engine binary
└── sigma-react-frontend/              # React 19 app (not Go)
```

---

## 2. cmd/ vs pkg/ vs internal/

### cmd/
- Entry points (binaries) -- one subdirectory per executable
- Main package lives here
- Thin -- delegates to `pkg/` for real logic
- Examples: `cmd/sigma_web/` (backend), `cmd/lia_recette/` (CLI)

### pkg/
- Libraries reusable across multiple cmd/ binaries
- No `main()`
- Public API intended for use by other packages
- Examples: `pkg/engine/`, `pkg/model/`, `pkg/validator/`

### internal/
- Private packages ONLY accessible to code under the same parent directory
- Go toolchain enforces: `internal/` is visible only to siblings and descendants of its parent
- LIA-SEC uses `internal/` sparingly; prefer clear `pkg/` boundaries
- When to use: helpers that MUST NOT leak to external consumers (e.g. `pkg/engine/internal/parser/`)

Decision tree:
```
Is it an entry point?       -> cmd/{binary-name}/
Is it reusable logic?       -> pkg/{domain-name}/
Is it implementation detail? -> pkg/{domain-name}/internal/
Is it a test helper only?    -> beside the tests (*_test_util.go)
```

---

## 3. The `cmd/sigma_web/` sub-module (R18 critical)

**This is the single most confusing thing about LIA-SEC Go layout.** Read carefully.

`cmd/sigma_web/` has its OWN `go.mod`:

```
module sigma_web_backend

go 1.25
```

This means:
- Commands run from `cmd/sigma_web/` use a DIFFERENT module than the root
- `go vet ./...` from the repo root does NOT scan `cmd/sigma_web/`
- `gosec` from the repo root returns Files=0 (silent failure)
- Tests must be run with `cd cmd/sigma_web && go test ./...`

Incident 2026-04-07: falsely claimed "multi-main blocks gosec" based on a wrong grep. Reality: sub-module boundary is the cause. See `.claude/rules/no-deduction-verify-facts.md` R18.

Correct invocations:
```bash
# Backend static analysis
cd cmd/sigma_web && ~/go/bin/gosec ./...
cd cmd/sigma_web && go vet ./...
cd cmd/sigma_web && go test -race ./...

# Build
cd cmd/sigma_web && ./build_secure_lia.sh

# Root module (pkg/*, cmd/lia_recette, etc.)
cd /opt/lia-sec/dev && go test ./pkg/...
```

---

## 4. build_secure_lia.sh whitelist (R1)

`cmd/sigma_web/build_secure_lia.sh` is an **explicit whitelist** of `.go` files to compile. It exists because:
- `go build .` compiles everything, including accidental leftover files
- The whitelist prevents shipping untested code (security leftover, debug scaffolding)
- It gives a single source of truth for what constitutes the backend

### Rule

**Every new `.go` file in `cmd/sigma_web/` MUST be added to `build_secure_lia.sh`** or it won't compile into the binary.

```bash
# Example line in build_secure_lia.sh
go build -o sigma_web_backend \
    cmd/sigma_web/backend_8081.go \
    cmd/sigma_web/foo_api.go \         # <-- add new files here
    cmd/sigma_web/bar_api.go \
    ...
```

Also register routes in `backend_8081.go`:
```go
RegisterFooRoutes(r) // add the call in the init section
```

### Archiving a file
To remove a file from the build WITHOUT deleting it:
```go
//go:build ignore
// +build ignore

// BOTH tags required for Go < 1.17 compatibility.
// Commented explanation on first line of header.

package main

// ... (file kept for reference, not compiled)
```

See `.claude/rules/enforcement-backend.md` and `.claude/rules/go-registration-checklist.md`.

---

## 5. Package naming

- **Lowercase single word**: `validator`, `engine`, `compliance`
- **No underscores, no camelCase**: NOT `rule_validator`, NOT `ruleValidator`
- **Singular usually**: `user`, not `users` (exception: collections that are the package's purpose)
- **Descriptive but terse**: `grc` is fine if context is clear; `gouvernance` is too long
- **Match the directory name**

LIA-SEC examples:
- `cmd/sigma_web/` -> `package main`
- `pkg/engine/code/` -> `package code`
- `pkg/validator/recipe/` -> `package recipe`
- `pkg/model/` -> `package model`

---

## 6. File naming

- **snake_case.go**: `foo_api.go`, `rule_parser.go`
- **Handlers**: `{domain}_api.go` or `{domain}_{action}.go` (e.g. `cve_enrichment_api.go`, `cve_attack_chain_api.go`)
- **Tests**: always `{basename}_test.go` alongside
- **Interfaces** (optional): `{domain}_interfaces.go` if interfaces are numerous
- **Types** (optional): `{domain}_types.go` if types justify separation
- **DO NOT** split a 100-line file into 5 files just because

Incident pattern: god-file (`discovery_api.go` at 3066 lines) was split into `discovery_api.go`, `discovery_results_api.go`, `discovery_cmdb.go`, ... Split only when a file exceeds ~500 lines OR when logically distinct concerns mix.

---

## 7. go.mod management

```bash
# Add a dependency
cd cmd/sigma_web && go get github.com/foo/bar@v1.2.3

# Upgrade all deps (with care)
cd cmd/sigma_web && go get -u ./...
cd cmd/sigma_web && go mod tidy

# Remove unused deps
cd cmd/sigma_web && go mod tidy
```

**Rules**:
- Pin specific versions (not `v1` or `master`)
- Run `go mod tidy` before committing `go.mod` / `go.sum` changes
- If a vuln is reported: follow R19 (fetch the current latest stable, not the minimum fixed version)
- Two go.mod files exist: ROOT + `cmd/sigma_web/`. Update BOTH if a shared dep changes (e.g. `github.com/gorilla/mux`).

---

## 8. Internal packages

Go enforces the `internal/` visibility rule. Use it when:
- A package is an implementation detail of `pkg/engine/` and should not be imported by `cmd/sigma_web/`
- Example structure:
```
pkg/engine/
├── engine.go              // public API
├── internal/
│   ├── parser/
│   │   └── parser.go     // only engine/ can import this
│   └── evaluator/
│       └── evaluator.go
```

**LIA-SEC rarely uses `internal/`**. Most `pkg/*` packages have simple public APIs. Add `internal/` only when abuse-prevention justifies it.

---

## 9. Vendoring status

LIA-SEC does NOT vendor dependencies. Modules are resolved from the module proxy (`proxy.golang.org`).

If offline builds are needed:
```bash
cd cmd/sigma_web && go mod vendor
# Commits vendor/ directory -- not our current practice
```

CI / deploy: depend on `proxy.golang.org`. Build offline fallback is the VPS `GOMODCACHE` (`~/go/pkg/mod`).

---

## Checklist for a new Go file in LIA-SEC

Before committing any new `.go` file:

- [ ] File is in the RIGHT directory (`cmd/` for binary, `pkg/` for lib, `pkg/*/internal/` for private)
- [ ] Filename is snake_case.go
- [ ] Package declaration matches directory name
- [ ] Imports use module paths (not relative)
- [ ] If in `cmd/sigma_web/`: added to `build_secure_lia.sh` whitelist
- [ ] If it has `RegisterXxxRoutes`: called from `backend_8081.go`
- [ ] Has `{file}_test.go` companion
- [ ] Functions prefixed by module if private (`treatmentTruncate`, not `truncate`)
- [ ] Doc comments on all exported identifiers
- [ ] Comments in English (R12)
