# Patterns de hardcoding detectes - LIA-SEC

## Patterns Go (.go)

| Pattern grep | Tag | Message correction |
|---|---|---|
| `localhost:[0-9]+` dans code | HARDCODE | `getCVEWorkerURL()` ou `getBackendUrl()` |
| `localhost:[0-9]+` dans commentaire `//` | COMMENT | `getCVEWorkerURL()` dans le commentaire |
| `127.0.0.1:[0-9]+` | HARDCODE | idem |
| `"https?://..."` hors localhost | HARDCODE | externaliser via env/config |
| `fmt.Println` / `fmt.Printf` | LOGGER | `LogSystemEvent("INFO", "MODULE", "ACTION", msg)` |

## Patterns TS/TSX (.ts, .tsx)

| Pattern grep | Tag | Message correction |
|---|---|---|
| `localhost:[0-9]+` dans code | HARDCODE | `getBackendUrl()` de ConfigurationService |
| `localhost:[0-9]+` dans commentaire `//` | COMMENT | `getBackendUrl()` dans le commentaire |
| `const.*URL.*= 'http...` | HARDCODE | `getBackendUrl()` de ConfigurationService |
| `console.log/error/warn/debug` | LOGGER | `customLogger.info/error/warn/debug(...)` |

## Patterns Python (.py)

| Pattern grep | Tag | Message correction |
|---|---|---|
| `localhost:[0-9]+` dans code | HARDCODE | `os.getenv()` ou fichier config |
| `localhost:[0-9]+` dans commentaire `#` | COMMENT | `os.getenv()` dans le commentaire |
| `127.0.0.1:[0-9]+` | HARDCODE | idem |
| `"https?://..."` hors localhost | HARDCODE | externaliser via `os.getenv()` ou config |
| `print(` | LOGGER | `logging.info/error/warning(...)` |

## Exclusions (ne pas signaler)

- Lignes `import` Go / `import` et `from` Python
- URLs de references officielles : `nvd.nist.gov`, `cisa.gov`, `attack.mitre.org`
- Fichiers de test (`*_test.go`, `*.test.ts`)

## Exit codes du script check_hardcodings.sh

| Code | Signification |
|---|---|
| `0` | OK — aucune violation |
| `1` | Violations trouvees — hook retourne `systemMessage` (non-bloquant) |
| `2` | Erreur usage — fichier non fourni ou inexistant |

## Integration hardcoding check dans security_check.sh

Ajouter dans chaque case (`*.go`, `*.ts|*.tsx`, `*.py`) apres gosec/semgrep, avant `;;` :

```bash
# Hardcoding check (code + commentaires)
# IMPORTANT: set -e dans le hook -> capturer exit avec ||
HARDCODE_SCRIPT="$(dirname "$0")/../skills/improve-hook/scripts/check_hardcodings.sh"
if [[ -x "$HARDCODE_SCRIPT" ]]; then
    HARDCODE_EXIT=0
    HARDCODE_OUT=$("$HARDCODE_SCRIPT" "$FILE_PATH" 2>&1) || HARDCODE_EXIT=$?
    if [[ "$HARDCODE_EXIT" -eq 1 ]]; then
        log "HARDCODE: violations trouvees dans $FILE_PATH"
        echo "HARDCODING WARNING:" >&2
        echo "$HARDCODE_OUT" >&2
        echo '{"continue": true, "systemMessage": "Hardcoding check: corrections requises. Voir violations ci-dessus."}'
        exit 0
    fi
fi
```

## Integration test-runner Go dans security_check.sh

Ajouter dans le case `*.go` APRES le bloc hardcoding, avant `;;`.
Ces blocs sont **bloquants** (exit 2) — ils empechent un Write/Edit si les tests echouent.

```bash
# Recipe validator tests
if [[ "$FILE_PATH" == *"pkg/validator/recipe/"* || "$FILE_PATH" == *"cmd/lia_recette/"* ]]; then
    log "Running recipe validator tests for $FILE_PATH"
    cd "${PROJECT_DIR}"
    TEST_OUTPUT=$(go test -mod=mod ./pkg/validator/recipe/ -timeout 30s 2>&1)
    TEST_EXIT=$?
    if [[ $TEST_EXIT -ne 0 ]]; then
        log "TESTS FAILED: $TEST_OUTPUT"
        echo "VALIDATOR TESTS FAILED:" >&2
        echo "$TEST_OUTPUT" | tail -20 >&2
        exit 2
    fi
    log "Recipe validator tests passed"
fi

# Ultimate validator tests
if [[ "$FILE_PATH" == *"pkg/validator/ultimate/"* ]]; then
    log "Running ultimate validator tests for $FILE_PATH"
    cd "${PROJECT_DIR}"
    TEST_OUTPUT=$(go test -mod=mod ./pkg/validator/ultimate/ -timeout 30s 2>&1)
    TEST_EXIT=$?
    if [[ $TEST_EXIT -ne 0 ]]; then
        log "TESTS FAILED: $TEST_OUTPUT"
        echo "ULTIMATE VALIDATOR TESTS FAILED:" >&2
        echo "$TEST_OUTPUT" | tail -20 >&2
        exit 2
    fi
    log "Ultimate validator tests passed"
fi

# ReportRule validator tests
if [[ "$FILE_PATH" == *"pkg/validator/reportrule/"* ]]; then
    log "Running reportrule validator tests for $FILE_PATH"
    cd "${PROJECT_DIR}"
    TEST_OUTPUT=$(go test -mod=mod ./pkg/validator/reportrule/ -timeout 30s 2>&1)
    TEST_EXIT=$?
    if [[ $TEST_EXIT -ne 0 ]]; then
        log "TESTS FAILED: $TEST_OUTPUT"
        echo "REPORTRULE VALIDATOR TESTS FAILED:" >&2
        echo "$TEST_OUTPUT" | tail -20 >&2
        exit 2
    fi
    log "Reportrule validator tests passed"
fi
```

## Conventions LIA-SEC (rappel)

```go
// CORRECT Go
LogSystemEvent("INFO", "CVE_PIPELINE", "TRIGGER", fmt.Sprintf("job %s pour %s", jobID, cveID))
url := getCVEWorkerURL() + "/api/create-rule"   // backend Go interne
url := getBackendUrl() + "/api/..."             // frontend -> backend
```

```typescript
// CORRECT TypeScript
import { getBackendUrl } from '../../services/ConfigurationService'
customLogger.info('API', 'Fetching pipeline queue', { endpoint })
const backendUrl = getBackendUrl()
```

```python
# CORRECT Python
import os, logging
BASE_URL = os.getenv("BACKEND_URL")
logging.info("Fetching %s", BASE_URL)
```
