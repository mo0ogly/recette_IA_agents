---
name: debug-go
description: Diagnostic et resolution systematique de bugs Go dans LIA-SEC. Se declenche quand un build Go echoue, un test Go plante, un handler retourne une erreur inattendue, un panic survient, ou quand l'utilisateur demande de debugger du code Go. Couvre le backend (cmd/sigma_web), le moteur (pkg/engine, pkg/model), la validation (pkg/validator), et la compliance (pkg/compliance).
---

# Debug Go - LIA-SEC v3.0

Methodologie multi-agent pour diagnostiquer et corriger les bugs Go dans LIA-SEC.
Principe : **PAS DE FIX SANS ROOT CAUSE D'ABORD.**

---

## Architecture Multi-Agent

| Etape | Role | Responsabilite |
|-------|------|----------------|
| 1. Reproduire le symptome | COLLECTOR | Capturer l'erreur complete (build, test, panic, runtime), collecter le contexte git |
| 2. Isoler la cause racine | ANALYST | Tracer le flux d'appels, identifier le fichier/ligne fautif, eliminer les fausses pistes |
| 3. Planifier le fix | PLANNER | Definir le fix minimal, estimer l'impact, lister les fichiers touches |
| 4. Appliquer + valider | EXECUTOR | Corriger, build, vet, test, verifier zero regression |
| 5. Documentation + tracabilite | LIBRARIAN | Plan, decision log, nettoyage debug logging temporaire |

---

## Quality Hooks

| Hook | Declenchement | Action |
|------|---------------|--------|
| `build-gate` | Apres chaque modification .go | `cd /opt/lia-sec/dev/cmd/sigma_web && ./build_secure_lia.sh` -- DOIT passer |
| `no-debug-residue` | Avant cloture du fix | Grep `"DEBUG", "DIAG"` dans les fichiers modifies -- ZERO match autorise |
| `regression-check` | Apres fix applique | `go vet ./cmd/sigma_web/...` + tests existants du package impacte |
| `diff-minimal` | Avant commit | `git diff --stat` -- le fix doit toucher le minimum de fichiers |

---

## Niveaux d'autonomie

| Niveau | Quand | Comportement |
|--------|-------|--------------|
| FULL_AUTO | Build error simple (import manquant, typo, fichier absent de build_secure_lia.sh) | Corriger et valider sans confirmation |
| SEMI_AUTO | Bug runtime avec cause racine identifiee dans 1 fichier | Proposer le fix, appliquer apres validation rapide |
| SUPERVISED | Bug multi-fichiers ou logique metier complexe | Plan detaille, validation de l'approche avant execution |
| MANUAL | Panic en production, corruption de donnees, race condition | Diagnostic complet, validation chaque etape, commit apres accord |

---

## Declenchement

- Build Go echoue (`go build`, `go vet`, `go test`)
- Panic / stack trace Go
- Handler API retourne 500 ou erreur inattendue
- Test unitaire echoue
- Comportement inattendu du moteur LIA-Scan
- L'utilisateur demande "debug", "pourquoi ca plante", "fix ce bug Go"

## Phase 1 : REPRODUIRE (COLLECTOR)

### Collecter l'erreur complete
```bash
# Build error
cd /opt/lia-sec/dev/cmd/sigma_web && ./build_secure_lia.sh 2>&1

# Test failure
go test ./pkg/... -v -run TestName 2>&1

# Runtime panic
./cleanup_services.sh backend
timeout 12 ./sigma_web_backend 2>&1 | head -50

# Moteur LIA-Scan
bin/lia_scan_engine -multi -rules . -events test_data.json -quadrigramme TEST -date $(date +%Y%m%d) 2>&1
```

### Questions a se poser
1. **Quand** ca a commence a casser ? (dernier commit qui marchait : `git log --oneline -10`)
2. **Ou** exactement l'erreur se manifeste ? (fichier:ligne du stack trace)
3. **Quoi** a change recemment ? (`git diff HEAD~3`)
4. **Reproductible** a chaque fois ou intermittent ?

## Phase 2 : ISOLER (ANALYST)

### Regle du 80/20
80% des bugs sont dans le code recemment modifie. Commencer par :
```bash
git diff --name-only HEAD~5 -- '*.go'
```

### Tracer le flux d'appels
1. Partir de l'erreur (fichier:ligne du stack trace)
2. Remonter la chaine d'appels : qui appelle cette fonction ?
3. Grep les callers : `grep -rn "nomDeLaFonction" cmd/ pkg/`
4. Identifier OU la donnee devient invalide (pas ou l'erreur apparait)

### Techniques de diagnostic

**Binary search avec git :**
```bash
git bisect start
git bisect bad HEAD
git bisect good <commit-qui-marchait>
# Puis tester a chaque etape : cd cmd/sigma_web && ./build_secure_lia.sh
```

**Logging strategique (temporaire) :**
```go
// TEMPORAIRE - a supprimer apres debug
logger.LogSystemEvent("DEBUG", "DIAG", "VARIABLE_X", fmt.Sprintf("%+v", variableX))
```
ATTENTION : utiliser `logger.LogSystemEvent`, JAMAIS `fmt.Println`.

**Verifier les types et nil :**
```go
// Panic frequente : nil pointer dereference
if obj == nil {
    logger.LogSystemEvent("ERROR", "DIAG", "NIL_POINTER", "obj is nil at function X")
    return fmt.Errorf("unexpected nil: obj in function X")
}
```

### Patterns de bugs frequents LIA-SEC

| Symptome | Cause probable | Ou chercher |
|----------|---------------|-------------|
| `undefined: functionName` | Import manquant ou fichier pas dans build_secure_lia.sh | Verifier `cmd/sigma_web/build_secure_lia.sh` |
| `cannot use X as Y` | Changement de signature d'interface | `pkg/model/` interfaces |
| Panic nil pointer | JSON unmarshalling de champ optionnel | Struct tags + validation |
| 500 sur route API | Erreur SQL non geree | `if err != nil` manquant |
| Moteur retourne 0 resultats | Operateur mal orthographie dans YAML | `pkg/model/modifiers.go` |
| Build OK mais runtime crash | Race condition | `go test -race ./...` |
| Handler pas appele | Route pas enregistree | `backend_8081.go` section routes |

## Phase 3 : CORRIGER (EXECUTOR)

### Regles de correction
1. **Fix minimal** : toucher le moins de fichiers possible
2. **Corriger LA CAUSE, pas le symptome** : si le bug est un nil pointer, trouver POURQUOI c'est nil
3. **Respecter les conventions LIA-SEC** :
   - `logger.LogSystemEvent()` pour le logging (R6)
   - Error wrapping : `fmt.Errorf("context: %w", err)`
   - Pas de `panic()` sauf `init()`
   - Pas de `_` sur les erreurs : `result, err := ...` toujours traite
4. **Verifier build_secure_lia.sh** : si nouveau fichier, l'ajouter au script de build

### Fix applique -> Gate obligatoire (Quality Hook build-gate)
```bash
# Build (TOUJOURS via build_secure_lia.sh)
cd /opt/lia-sec/dev/cmd/sigma_web && ./build_secure_lia.sh

# Vet (analyse statique)
go vet ./cmd/sigma_web/...

# Test si applicable
go test ./pkg/... -v -run TestRelated

# Si moteur impacte
bin/lia_scan_engine -multi -rules . -events test_data.json -quadrigramme TEST -date $(date +%Y%m%d)
```

## Phase 4 : VALIDER (ANALYST + Quality Hook no-debug-residue)

1. **Reproduire le scenario original** : le bug ne doit plus apparaitre
2. **Regression** : les tests existants passent toujours
3. **Diff propre** : `git diff` ne contient que le fix, pas de debug residuel
4. **Pas de debug logging reste** : supprimer tous les `logger.LogSystemEvent("DEBUG", "DIAG", ...)` temporaires
5. **Anti-patterns verifies** : pas de fmt.Println, pas de localhost hardcode, pas de console.log

## Commandes utiles

```bash
# Stack trace lisible
cd /opt/lia-sec/dev/cmd/sigma_web && ./build_secure_lia.sh 2>&1 | head -30

# Trouver toutes les references a une fonction
grep -rn "functionName" cmd/ pkg/ --include="*.go"

# Trouver les TODO/FIXME oublies
grep -rn "TODO\|FIXME\|HACK\|XXX" cmd/ pkg/ --include="*.go"

# Lister les fichiers Go modifies recemment
git log --oneline --name-only --diff-filter=M -- '*.go' | head -30

# Tester un package specifique
go test -v -count=1 ./pkg/validator/recipe/...

# Race detection
go test -race ./pkg/...

# Verifier les imports inutilises
go vet ./...
```

## Escalade

Si apres 3 tentatives le bug n'est pas resolu :
1. Documenter ce qui a ete essaye
2. Poser la question autrement (Bloc 2 CLAUDE.md)
3. Chercher si quelqu'un a eu le meme probleme (WebSearch agent)
4. Decomposer le probleme en sous-problemes plus petits

---

## Adaptation et Replanification

- **2 echecs consecutifs** (ex: fix A casse autre chose + fix B ne compile pas) -> invoquer `/replan`
- **Jamais improviser** : si la cause racine n'est pas identifiee, NE PAS appliquer de fix speculatif
- **Fallback** : si git bisect echoue, passer au logging strategique ; si le logging ne suffit pas, isoler dans un test unitaire minimal
- **Replanification documentee** : chaque changement d'approche est trace dans le decision log

---

## Tracabilite (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_DEBUG_GO_{ID}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"debug-go-{id}","action":"ACTION","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_DEBUG_GO_{ID}_{DATE}.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

### Action journal
Maintenir un journal d'actions dans le plan persistant :
```
[HH:MM] COLLECTOR - Erreur capturee: "undefined: RegisterXxxRoutes" dans build
[HH:MM] ANALYST - Cause: fichier xxx.go absent de build_secure_lia.sh
[HH:MM] EXECUTOR - Ajout dans build_secure_lia.sh, build OK
[HH:MM] ANALYST - Regression check: go vet OK, tests OK
[HH:MM] LIBRARIAN - Plan clos, debug logging nettoye
```

---

## Scoring Agentique (/50)

| Critere | Points | Description |
|---------|--------|-------------|
| C1 Decomposition | /10 | Symptome reproduit, erreur complete capturee, contexte git collecte |
| C2 Planification | /10 | Cause racine identifiee AVANT le fix, impact estime correctement |
| C3 Replanification | /10 | Gestion des echecs (fix qui casse autre chose), adaptation methodique |
| C4 Outillage dynamique | /10 | Utilisation correcte des hooks (build-gate, no-debug-residue, regression-check) |
| C5 Tracabilite | /10 | Plan persistant, decision log, action journal, zero debug logging residuel |
