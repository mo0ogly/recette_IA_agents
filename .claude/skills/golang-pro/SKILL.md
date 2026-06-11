---
name: golang-pro
description: Write idiomatic, production-grade Go code for LIA-SEC backend (cmd/sigma_web) and moteur (pkg/). Covers interface-first design, concurrency with goroutines/channels/context, generics, table-driven tests with -race, benchmarks with pprof, and integration with LIA-SEC conventions (LogSystemEvent, mux.Router, build_secure_lia.sh, R1-R24). Use when writing a new Go package, handler, service, or refactoring existing Go code for idiomaticity. Triggers on "write Go", "implement in Go", "new Go package", "Go interface", "goroutine", "channel", "Go generics", "gRPC Go", "Go service", "Go handler", "Go benchmark", "Go fuzzing", "refactor Go". Complements /go-recette (audit), /debug-go (bug fix), and /test-first (test enforcement).
---

# Golang Pro -- LIA-SEC Idiomatic Go Writer

Senior Go implementer for LIA-SEC. Produces idiomatic Go 1.25+ code that **passes `/go-recette` on first run**, composes small focused interfaces, uses context propagation everywhere, and ships with table-driven tests under `-race`.

Scope: implementation (write code). For bugs: `/debug-go`. For audit: `/go-recette`. For test enforcement: `/test-first`.

## Core Workflow (6 steps)

1. **Analyze** -- read the module structure (`cmd/sigma_web/` or `pkg/...`), existing interfaces, surrounding conventions. `grep` similar handlers/services.
2. **Design interfaces** -- small, focused, composition over inheritance. Load `references/interfaces.md` when designing a new contract.
3. **Implement** -- write code using LIA-SEC conventions (Constraints below). Load the relevant reference:
   - Concurrency (goroutine/channel/context) -> `references/concurrency.md`
   - Generics -> `references/generics.md`
   - Package layout (cmd/ vs pkg/ vs internal/) -> `references/project-structure.md`
4. **Lint & vet** -- run `go vet` and `golangci-lint run`, fix ALL reported issues before proceeding.
5. **Test** -- table-driven tests with `-race`. Coverage >= 80% on new code. Load `references/testing.md`.
6. **Validate** -- build via `build_secure_lia.sh`, smoke test via `httptest`, confirm zero regressions.

Every step gated by the Verification Gate.

## Decomposition des sous-taches

Au demarrage, decomposer toute demande en sous-taches independantes :

- [ ] Sous-tache 1 : reads / greps pour cartographier le contexte existant
- [ ] Sous-tache 2 : design des interfaces publiques du package
- [ ] Sous-tache 3 : implementation minimale (contract first, no cruft)
- [ ] Sous-tache 4 : tests table-driven + race detector
- [ ] Sous-tache 5 : registration dans `build_secure_lia.sh` + `backend_8081.go` si handler
- [ ] Sous-tache 6 : golangci-lint + go vet + build gate

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour toute creation de package/handler non trivial (> 3 fichiers ou > 200 lignes) :

1. Creer `_alire/tracking/PLAN_GOLANG_PRO_{FEATURE}_{YYYY-MM-DD}.md` avant d'ecrire une seule ligne de code.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une modification ponctuelle (< 3 fichiers) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: build fail + fix qui casse autre chose) :

- STOP
- Invoquer `/replan` -> produit `PLAN_GOLANG_PRO_*_REPLAN_*.md`
- NE PAS improviser un contournement

Declencheurs typiques :
- Build echoue apres fix -> REPLAN
- Test casse apres refactor -> REPLAN
- Interface conflit avec package existant -> REPLAN

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Explorer le code existant avant d'ecrire | N/A |
| `Write`, `Edit` | Creer/modifier fichiers .go | N/A |
| `Bash go vet`, `Bash go test`, `Bash golangci-lint run` | Validation locale | 1 retry sur flakiness |
| `Bash build_secure_lia.sh` | Build gate (R1 Go whitelist) | Echec -> diagnose, pas de retry aveugle |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(test-first)` | Apres creation handler | Obligatoire |
| `Skill(go-recette)` | Apres fin implementation | Obligatoire avant commit |

Selection dynamique : outil choisi selon le contexte, pas de liste figee.

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix d'architecture (nouvelle interface, nouveau package)
- Rejet d'une alternative (ex: sync.Mutex vs channel)
- Trade-offs (performance vs lisibilite, generique vs concret)

Format :
```json
{"timestamp":"...","session":"golang-pro-{feature}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_GOLANG_PRO_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_GOLANG_PRO_YYYY-MM-DD.md`.

## Constraints (MUST DO / MUST NOT DO)

### MUST DO

- `gofmt` + `golangci-lint run` clean sur tout code livre
- `context.Context` sur toute fonction IO-bound, blocking, SQL, HTTP, goroutine
- Error wrapping : `fmt.Errorf("operation failed: %w", err)` -- jamais `errors.New(err.Error())`
- Table-driven tests + `-race` sur tout package avec goroutines
- Doc comments sur TOUS les exported (types, fonctions, packages)
- Functional options ou PostgreSQL `system_variables` pour la config (pas de globales mutables)
- `*mux.Router` comme type explicite pour les `RegisterXxxRoutes` (R4)
- `LogSystemEvent("LEVEL", "COMPONENT", "ACTION", details)` pour tout log applicatif (R6)
- `setCORSHeaders(w); if r.Method == "OPTIONS" { ... }` en premiere ligne de tout handler
- Function names prefixes par le module (`treatmentTruncate`, pas `truncate`) pour eviter collisions
- Commentaires en anglais (R12)
- Enregistrer tout nouveau fichier `cmd/sigma_web/*.go` dans `build_secure_lia.sh` (R1 whitelist)

### MUST NOT DO

- `log.Printf`, `log.Println`, `fmt.Println` pour logs (sauf 13 exceptions early-init documentees)
- `panic()` sauf dans `init()` ou cas irrecuperable documente
- `_ = err` sans justification dans un commentaire adjacent
- Goroutines sans lifecycle clair (context cancellation ou WaitGroup)
- `sql.Open()` dans un handler (reutiliser le `db *sql.DB` global)
- Construction manuelle JSON via `fmt.Fprintf(w, ...)` -- toujours `json.NewEncoder(w).Encode(...)`
- `InsecureSkipVerify: true` sans justification documentee
- Provider/URL/modele IA hardcode (R5 PostgreSQL First, voir `.claude/rules/ai-architecture.md`)
- Emoji dans code, commentaires, logs, variables (R10)
- References a Nuclei/Wappalyzer/Nmap dans commentaires ou noms (R13)

## Reference Guide (load on demand)

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Concurrency patterns | `references/concurrency.md` | Goroutines, channels, select, sync primitives, worker pools, fan-out/fan-in |
| Interface design | `references/interfaces.md` | New package contract, io.Reader/Writer composition, mocking strategy |
| Generics (Go 1.21+) | `references/generics.md` | Type parameters, constraints, comparable, generic slice/map helpers |
| Testing & benchmarks | `references/testing.md` | Table-driven tests, httptest, benchmarks, pprof, fuzzing |
| Project structure | `references/project-structure.md` | cmd/ vs pkg/ vs internal/, go.mod sub-modules (LIA-SEC has one) |

Keep SKILL.md lean: consult these only for the task at hand.

## LIA-SEC Quick Reference

### File locations
- Backend HTTP handlers : `cmd/sigma_web/*.go` (sub-module, own `go.mod` = `sigma_web_backend`)
- Moteur LIA-Scan : `pkg/engine/code/`, `pkg/model/`
- Validators : `pkg/validator/` (recipe, reportrule, ultimate)
- Shared utils : `pkg/utils/` (yamlconv, etc.)
- Compliance engine : `pkg/compliance/`

### Registration checklist for a new handler file in `cmd/sigma_web/`

1. `cmd/sigma_web/{file}.go` -- implementation with `RegisterXxxRoutes(r *mux.Router)`
2. `cmd/sigma_web/{file}_test.go` -- table-driven tests + `httptest.NewRecorder()`
3. Add `cmd/sigma_web/{file}.go \` to `build_secure_lia.sh` whitelist
4. Add `RegisterXxxRoutes(r)` call in `backend_8081.go` init section
5. Run `cd /opt/lia-sec/dev/cmd/sigma_web && ./build_secure_lia.sh` -- MUST pass
6. Invoke `/test-first` if not already done
7. Invoke `/go-recette cmd/sigma_web/{file}.go` before commit

### Canonical handler skeleton

```go
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "net/http"

    "github.com/gorilla/mux"
)

// RegisterFooRoutes wires the /api/foo routes onto the provided router.
// Must be invoked from backend_8081.go during startup.
func RegisterFooRoutes(r *mux.Router) {
    r.HandleFunc("/api/foo/list", fooList).Methods("GET", "OPTIONS")
    r.HandleFunc("/api/foo/{id}", fooGet).Methods("GET", "OPTIONS")
    LogSystemEvent("INFO", "FOO", "INIT", "Foo API initialized (2 endpoints)")
}

// fooList returns the paginated list of foos.
func fooList(w http.ResponseWriter, r *http.Request) {
    setCORSHeaders(w)
    if r.Method == http.MethodOptions {
        w.WriteHeader(http.StatusOK)
        return
    }

    ctx := r.Context()
    items, err := fooListFromDB(ctx)
    if err != nil {
        LogSystemEvent("ERROR", "FOO", "LIST_FAILED", err.Error())
        http.Error(w, "internal error", http.StatusInternalServerError)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    if err := json.NewEncoder(w).Encode(map[string]any{
        "success": true,
        "data":    items,
    }); err != nil {
        LogSystemEvent("ERROR", "FOO", "ENCODE_FAILED", err.Error())
    }
}

// fooListFromDB queries the foo table; caller must pass a cancellable context.
func fooListFromDB(ctx context.Context) ([]Foo, error) {
    rows, err := db.QueryContext(ctx, "SELECT id, name FROM foos ORDER BY created_at DESC LIMIT 100")
    if err != nil {
        return nil, fmt.Errorf("query foos: %w", err)
    }
    defer rows.Close()

    var out []Foo
    for rows.Next() {
        var f Foo
        if err := rows.Scan(&f.ID, &f.Name); err != nil {
            return nil, fmt.Errorf("scan foo: %w", err)
        }
        out = append(out, f)
    }
    if err := rows.Err(); err != nil {
        return nil, fmt.Errorf("iterate foos: %w", err)
    }
    return out, nil
}
```

Demonstrates: CORS + OPTIONS, context propagation, error wrapping, LogSystemEvent, defer Close, envelope `{success, data}` (R17 consumer-side unwrap), pagination.

## Output Templates

When implementing a new Go feature, deliver in this order:

1. **Interfaces** (contracts first) -- one file ending in `_interfaces.go` or top of main file
2. **Implementation** -- one or more `.go` files, each < 500 lines
3. **Tests** -- `*_test.go` alongside, table-driven, `-race` ready
4. **Registration** -- entry added to `build_secure_lia.sh` + `backend_8081.go`
5. **Brief explanation** -- 3-5 lines max expliquant les choix non-obvious (concurrency, generics, trade-off). Post-delivery, not inline.

## Integration with APEX / PDCA

- **APEX Phase 3 BUILD** : invoke this skill when implementing new Go packages. The 6-step workflow maps onto APEX's OODA loop.
- **PDCA Phase D DO** : invoke for Go refactors in the `architecture` or `code_hygiene` domain. Pipelines gates (5 Go gates) are executed post-implementation; this skill ensures idiomaticity AT implementation time.
- **R17 Contract Gate** : Go handlers must ship with `_test.go` using `httptest.NewRequest` + envelope assertion. This skill bakes it into Output Template step 3.

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `cd /opt/lia-sec/dev/cmd/sigma_web && ./build_secure_lia.sh` exits 0
- [ ] `go vet ./cmd/sigma_web/...` clean
- [ ] `golangci-lint run ./cmd/sigma_web/...` clean (ou uniquement issues pre-existantes)
- [ ] `go test -race -count=1 ./cmd/sigma_web/... -run TestFoo` passe pour les nouveaux tests
- [ ] Nouveau fichier enregistre dans `build_secure_lia.sh` (pour `cmd/sigma_web/*.go`)
- [ ] Nouveau `RegisterXxxRoutes` wired dans `backend_8081.go` (pour nouvelles routes HTTP)
- [ ] `/go-recette {path}` score >= 36/41 et zero CRITIQUE en FAIL
- [ ] Endpoint repond 200 sur live smoke test (R17 E3)

Si un gate echoue : STOP, fix, re-gate. JAMAIS declarer "done" avec un gate rouge.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs ? | /10 |
| C4 Outillage : outils choisis dynamiquement + /go-recette + /test-first invoques ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Related

- `/go-recette` -- audit apres implementation (41-check validation)
- `/debug-go` -- diagnose bugs in existing Go code
- `/test-first` -- enforce `_test.go` creation alongside handlers
- `/db-schema-designer` -- when new package needs a new PostgreSQL table
- `.claude/rules/enforcement-backend.md` -- 42 files migrated, conventions encoded
- `.claude/rules/go-registration-checklist.md` -- file registration rules
- `.claude/rules/ai-architecture.md` -- if code calls AI providers
- `.claude/rules/apex-pdca-v6-guide.md` -- integration with agentic loops
- `cmd/sigma_web/AI_ARCHITECTURE.md` -- AI provider patterns
