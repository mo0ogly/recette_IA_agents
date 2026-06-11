# Build Pipeline Go -- Reference partagee APEX & PDCA v6.0

> Pipeline obligatoire pour chaque fichier Go cree ou modifie.
> Integre : debug-go methodologie, test-first, go-recette gates, go-registration-checklist.

---

## Pipeline sequentiel (chaque fichier .go)

```
EDIT/WRITE .go
    |
    v
STEP 1: build_secure_lia.sh
    |-- Si nouveau fichier cmd/sigma_web/ : ajouter au script AVANT build
    |-- cd cmd/sigma_web && ./build_secure_lia.sh
    |-- FAIL -> STOP, corriger, re-build
    |-- [CONCURRENT-SAFE] le script prend un flock exclusif
    |   (cmd/sigma_web/.build_secure_lia.lock). Si un autre build
    |   tourne (autre agent/session/skill), CELUI-CI ATTEND la fin
    |   du premier au lieu de racer le cache+source -> plus de
    |   false-fail transitoire (incident 2026-05-16
    |   fingerprint_port_hints). Aucune action requise cote skill :
    |   tout build passe par ce chokepoint unique et herite du verrou.
    |   NE JAMAIS contourner avec `go build .` direct (perd le verrou
    |   ET viole la whitelist R9).
    |
    v
STEP 2: RegisterRoutes (si handler HTTP)
    |-- func RegisterXxxRoutes(r *mux.Router) { ... }
    |-- Ajouter RegisterXxxRoutes(r) dans backend_8081.go
    |-- Signature TOUJOURS *mux.Router (PAS d'interface anonyme)
    |-- Prefixer les noms de fonctions par module (pas truncate, mais treatmentTruncate)
    |
    v
STEP 3: go vet
    |-- cd cmd/sigma_web && GOFLAGS="" go vet . 2>&1
    |-- 0 erreurs = PASS
    |-- FAIL -> STOP, corriger
    |
    v
STEP 4: test-first
    |-- Creer {file}_test.go dans le meme package
    |-- Minimum : 1 test nominal + 1 test erreur + 1 test limite
    |-- go test -v -run TestXxx ./pkg/... ou ./cmd/sigma_web/
    |-- PASS = continuer, FAIL = corriger le CODE (pas le test)
    |
    v
STEP 5: Verification imports
    |-- Chaque import utilise (le hook PostToolUse bloque sur import inutile)
    |-- Pas de fmt.Println, log.Printf (R6 LogSystemEvent)
    |-- Pas de localhost hardcode (R5 ConfigurationService)
    |
    v
STEP 6: BUILD-INFO VERIFICATION (post-deploy si backend redemarre)
    |-- Apres deploy + systemctl restart lia-backend :
    |-- curl -s http://localhost:8081/api/diagnostic/build-info | jq .commit_hash
    |-- Doit correspondre a: git rev-parse --short HEAD
    |-- Si mismatch = STALE BINARY (le binary deploye ne contient PAS le fix)
    |-- Incident 2026-04-13 : fix nis2_db.go absent du binary malgre build OK
    |   -> 2h de debug pour detecter que le binary etait un cache ancien
    |-- Rebuild manuel + copy + restart si mismatch detecte
    |
    v
GATE PASSED -> fichier pret pour la phase RECETTE
```

---

## Regles de construction Go (R1-R18)

### Fichier nouveau dans cmd/sigma_web/

1. **build_secure_lia.sh** : ajouter `cmd/sigma_web/{filename}.go \` dans la liste
2. **backend_8081.go** : ajouter `RegisterXxxRoutes(r)` si handler HTTP
3. **Signature** : `func RegisterXxxRoutes(r *mux.Router)`
4. **LogSystemEvent** dans l'init : `LogSystemEvent("INFO", "XXX", "INIT", "XXX API initialized (N endpoints)")`
5. **setCORSHeaders + OPTIONS** en debut de chaque handler :
   ```go
   setCORSHeaders(w)
   if r.Method == "OPTIONS" { w.WriteHeader(200); return }
   ```

### Nommage fonctions

- TOUJOURS prefixer par module : `treatmentTruncate`, `discoveryNilIfEmpty`, `cveParseDate`
- JAMAIS : `truncate`, `nilIfEmpty`, `parseDate` (collision 600+ fichiers)

### Error handling

- `result, err := ...` TOUJOURS traite (pas de `_`)
- `fmt.Errorf("context: %w", err)` pour wrapping
- `defer rows.Close()` apres tout `db.Query`
- `defer f.Close()` apres tout `os.Open`

### Logging

```go
// CORRECT
LogSystemEvent("INFO", "COMPONENT", "ACTION", fmt.Sprintf("details: %v", value))

// INTERDIT
fmt.Println("Processing:", ruleID)
log.Printf("Processing: %s", ruleID)
```

### SQL

```go
// CORRECT : prepared statements
db.Query("SELECT * FROM table WHERE col = $1", value)

// INTERDIT : injection
db.Query(fmt.Sprintf("SELECT * FROM table WHERE col = '%s'", value))
```

### Tests (patterns test-first)

**Go unit test :**
```go
func TestNomFonction_CasNormal(t *testing.T) {
    // Arrange
    input := prepareTestInput()
    // Act
    result, err := FonctionTestee(input)
    // Assert
    if err != nil { t.Fatalf("unexpected error: %v", err) }
    if result.Count != 5 { t.Errorf("expected 5, got %d", result.Count) }
}
```

**API test bash (handlers) :**
```bash
#!/bin/bash
set -e
API_BASE_URL="${API_BASE_URL:-http://localhost:8081}"
RESPONSE=$(curl -s -w "\n%{http_code}" "$API_BASE_URL/api/endpoint")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
[ "$HTTP_CODE" = "200" ] && echo "PASS" || { echo "FAIL (HTTP $HTTP_CODE)"; exit 1; }
```

---

## Debug Go (methodologie debug-go integree)

Quand un build/test echoue pendant le pipeline :

### Phase 1 : REPRODUIRE
```bash
cd cmd/sigma_web && ./build_secure_lia.sh 2>&1 | head -30
```

### Phase 2 : ISOLER
```bash
git diff --name-only HEAD~5 -- '*.go'  # 80% des bugs = code recent
grep -rn "nomFonction" cmd/ pkg/       # tracer callers
```

### Phase 3 : CORRIGER
- Fix minimal (moins de fichiers possible)
- Corriger LA CAUSE pas le symptome
- Si nil pointer : trouver POURQUOI c'est nil

### Phase 4 : VALIDER
- Reproduire scenario original (bug disparu)
- Regression check (tests existants passent)
- Diff propre (pas de debug residuel)
- Grep "DEBUG", "DIAG" = 0 match

### Replanification
- 2 echecs consecutifs -> invoquer `/replan`
- JAMAIS improviser : cause racine identifiee AVANT fix
- Fallback : git bisect -> logging strategique -> test unitaire minimal

---

## Score pipeline Go /5

| Critere | Points | Quand 1 point |
|---------|--------|---------------|
| build_secure_lia.sh passe | /1 | exit 0 |
| RegisterRoutes + backend_8081.go | /1 | Si handler, route enregistree |
| go vet clean | /1 | 0 erreurs |
| test-first (_test.go existe + passe) | /1 | exit 0 |
| Conventions (R6, R5, R12, R13) | /1 | 0 violation |
