# Recette Protocol -- Reference partagee APEX & PDCA v6.0

> 5 etapes sequentielles BLOQUANTES. Chaque etape doit passer avant la suivante.
> Integre : /go-recette (41 checks), /react-recette (48 checks), Playwright, R25/R21/R23 Design Audit, R17 Contract Gate.

---

## Vue d'ensemble

```
ETAPE 0: ENGINE DELTA (c37 A40 -- si fichiers pkg/fingerprint/* modifies)
    |-- BLOQUANT : zero CORRECT regression vs baseline
    |
    v
ETAPE 1: STATIC (go-recette + react-recette)
    |-- BLOQUANT : score minimum requis
    |
    v
ETAPE 2: RUNTIME (Playwright smoke test)
    |-- BLOQUANT : zero Component Error
    |
    v
ETAPE 2bis: DESIGN AUDIT (R25/R21/R23 -- si fichiers .tsx modifies)
    |-- BLOQUANT : zero pattern A-H, WCAG AA >= 4.5:1 sur 6 themes
    |
    v
ETAPE 3: CONTRACT (R17 -- si composants API)
    |-- BLOQUANT : fixture + render-test + smoke
    |
    v
ETAPE 4: REGRESSION (delta scoring)
    |-- BLOQUANT : zero regression > 5 points
    |
    v
RECETTE PASSED -> Phase suivante (COMPLETE/FINALIZE)
```

---

## Etape 0 : ENGINE DELTA (c37 A40 -- MANDATORY pour pkg/fingerprint/* changes)

Avant tout commit qui modifie `pkg/fingerprint/loader.go`, `pkg/fingerprint/model.go`, `pkg/fingerprint/matcher.go`, ou tout autre fichier `pkg/fingerprint/*.go`, executer :

```bash
bash /opt/lia-sec/dev/.claude/skills/liaprobe-fingerprint-rebuild/scripts/verify_engine_delta.sh
```

Le script :
1. `git stash push --include-untracked` les changes courants
2. `make recette` rebuild baseline (liaprobe + recette-onyphe propres)
3. `recette-onyphe` -> PRE verdict counts (CORRECT / MISS / WRONG)
4. `git stash pop` restore working tree
5. `make recette` rebuild avec changes
6. `recette-onyphe` -> POST verdict counts
7. Print DELTA + exit non-zero si CORRECT regression > threshold

Defaut : threshold = 0 (toute regression CORRECT bloque).

**Incident origine** : c36 A34 -- loader.go filter caused CORRECT 15200 -> 12267 regression (-2933). Filter logic was conceptually wrong (permanent_doubtful = metadata != engine-scan-skip). Script aurait revele la regression avant le commit. Documente dans `.claude/skills/liaprobe-fingerprint-rebuild/SKILL.md` section "permanent_doubtful is METADATA, not engine-scan-skip".

**Trigger conditions** :
- Modification d'un fichier dans `liaprobe/pkg/fingerprint/*.go`
- Modification de la structure d'un pattern JSON (champ ajoute/retire/renomme)
- Modification du loader.go validation logic
- Ajout d'un nouveau matcher type ou probe type

**Skip conditions** (avec justification explicite dans action_journal.jsonl) :
- Pas de pkg/fingerprint/* dans le changeset
- Skill-only changes (scripts/, SKILL.md)

---

## Etape 1 : STATIC

### Pour chaque fichier .go modifie dans le cycle

Invoquer via Skill tool (delegation obligatoire, pas de grep manuel) :
```
Skill({skill: "go-recette", args: "{fichier ou repertoire}"})
```

**41 checks :**
- Bloc A conventions (10) : LogSystemEvent, ConfigurationService, build whitelist, RegisterRoutes, CORS, naming, comments EN, no source attribution, defer cleanup, R16
- Bloc B OWASP (10) : SQLi, CmdInj, secrets, auth, path traversal, error disclosure, security logging, input validation, TLS, context
- Bloc C archi/perf (10) : no stub, no mock, goroutine cleanup, error wrapping, no CORS dup, connection pool, JSON encoding, UUID validation, pagination, _test.go
- Bloc D static analysis (3) : gosec, govulncheck, go vet
- Bloc E R17 Go Contract Gate (4) : test file, test execution, live smoke, response envelope
- Bloc G migration health (4) : no SQLite compiled, registered routes, build ignore, no type redeclaration

**Verdicts :**
- >= 36/41 ET 0 critique : PASS
- 28-35 OU majeur : "Corrections requises"
- < 28 OU critique : "NE PAS INTEGRER"
- Bloc E FAIL = bloquant

### Pour chaque fichier .tsx/.ts modifie dans le cycle

Invoquer via Skill tool :
```
Skill({skill: "react-recette", args: "{fichier ou repertoire}"})
```

**48 checks :**
- Bloc A conventions (10) : MUI Grid v7, no hardcoding URL, logger, no mock, couleurs theme, polices, overflow, z-index, fetch error handling, TS strict
- Bloc B OWASP (10) : XSS, secrets, validation, error disclosure, storage, redirections, prototype pollution, content security, deps vulns, secrets in logs
- Bloc C Vercel performance (20) : imports directs, Promise.all, dependencies primitives, memo, setState fonctionnel, lazy init, rendu conditionnel, cache localStorage, event listeners, JSX hisse, await differe, etat derive, lecture differee, startTransition, content-visibility, Map lookups, iterations fusionnees, early return, SWR/React Query, handlers refs
- Bloc D react-doctor : PASS/FAIL
- Bloc E R17 Contract Gate (4) : fixture, render-assert, smoke Playwright, unwrap envelope
- Bloc F legacy health (4) : fetchWithConfig, no raw fetch, no API_BASE_URL, no console.*

**Verdicts :**
- >= 36/40 (A+B+C) ET 0 critique : PASS
- 28-35 OU majeur : "Corrections requises"
- < 28 OU critique : "NE PAS INTEGRER"
- Bloc E FAIL = bloquant

### Integration scoring PDCA

```
security domain score = (go-recette BLOC B + BLOC D) / 20 * 20
                    OU  react-recette BLOC B / 10 * 20
```

### Cycle FAILURE si :
- Score /go-recette < 36/41 OU /react-recette < 36/40
- OU un seul check Bloc E (R17) en FAIL
- OU un check CRITIQUE en FAIL

---

## Etape 2 : RUNTIME

Apres les checks statiques, valider en runtime sur les pages impactees.

```
Pour chaque page/composant modifie :
  1. mcp__playwright__browser_navigate -> URL de la page
  2. mcp__playwright__browser_snapshot -> capturer le DOM
  3. Chercher dans le snapshot :
     - "Component Error"
     - "is not a function"
     - "Cannot read properties of"
     - "undefined"
     - Stack traces React
  4. Si un seul match : FAILURE -> corriger -> re-tester
```

**Pages principales a tester (si scope large) :**
- Dashboard (/dashboard)
- Discovery (/discovery)
- Analysis (/analysis)
- Admin (/admin)
- Compliance (/compliance)

**Pattern de correction crash runtime :**
```tsx
// Avant (crash si items null)
{data.items.map(item => ...)}

// Apres (safe)
{(data.items || []).map(item => ...)}
```

Incident reference : 2026-04-06, 9 composants crashes en prod avec `.map()` sur null.

---

## Etape 2bis : DESIGN AUDIT (R25/R21/R23)

S'applique si le cycle a cree ou modifie AU MOINS UN fichier `.tsx`.

Invoquer via Skill tool (delegation obligatoire) :
```
Skill({skill: "frontend-design", args: "audit R25 R21 R23 WCAG scope: {liste composants}"})
```

**Scope obligatoire** : composants modifies dans le cycle ET tous les composants
transitivisement importes (depth >= 2). Raison : incident 2026-04-24 —
`UnifiedResultsTreeView.tsx` vivait dans `components/system/` hors scope du cycle
qui ne ciblait que `components/reports/`.

**Patterns verifies (A-H) :**

```bash
# Pattern A -- dark hex gradients sans useTheme
grep -rnE "linear-gradient\([^)]*#[0-4][0-9a-fA-F]{3,5}" --include="*.tsx" \
  sigma-react-frontend/src/ | grep -v "/themes/\|/constants/\|_archive/"

# Pattern B -- color: 'white'/'black' sans theme adjacency
for f in $(grep -rlE "color: '(white|black)'" --include="*.tsx" \
  sigma-react-frontend/src/ | grep -v "/themes/\|/constants/\|_archive/"); do
  grep -q "useTheme\|contrastText\|theme.palette.getContrastText" "$f" || echo "$f"
done

# Pattern C -- couleur hex hardcodee hors bg/gradient
grep -rnE "color: '#[0-9a-fA-F]{3,6}'" --include="*.tsx" sigma-react-frontend/src/ | \
  grep -v "/themes/\|/constants/\|_archive/"

# Pattern D -- bgcolor hex hardcoded
grep -rnE "bgcolor: '#[0-9a-fA-F]{3,8}'" --include="*.tsx" sigma-react-frontend/src/ | \
  grep -v "/themes/\|/constants/\|_archive/"

# Pattern E -- background property hex direct
grep -rnE "background: '#[0-9a-fA-F]{3,6}'" --include="*.tsx" sigma-react-frontend/src/ | \
  grep -v "/themes/\|/constants/\|_archive/"

# Pattern F -- rgba(0,0,0) component backgrounds (not modal backdrop)
grep -rn "bgcolor: 'rgba(0,0,0" --include="*.tsx" sigma-react-frontend/src/ | \
  grep -v "position: 'fixed'" | grep -v "/themes/"

# Pattern G -- R21 Dialogs sans maxHeight 90vh
grep -rn "<Dialog" --include="*.tsx" sigma-react-frontend/src/ | \
  grep -v "maxHeight\|/themes/\|_archive/" | grep -v "//.*<Dialog"

# Pattern H -- R23 radars/charts sans labels externes
grep -l "Radar\|Bubble\|Scatter" sigma-react-frontend/src/components/**/*.tsx 2>/dev/null | \
  xargs grep -L "angularExternalLabels\|deOverlapLabels" 2>/dev/null
```

**WCAG AA verification** via `/frontend-design` : rendre chaque composant en scope
sur les 6 themes actifs (Cyber, CyberMatrix, CyberRed, Classic, Heaven, Default)
et mesurer le contraste de chaque noeud Typography.

Seuils WCAG AA :
- Texte normal : >= 4.5:1
- Large text (>= 18px ou >= 14px bold) : >= 3:1

**FAIL** = pattern A/B/C/D/E/F/G/H trouve OU contraste < seuil sur un theme -> corriger, retourner Phase D, re-executer Etape 2bis.

---

## Etape 3 : CONTRACT (R17)

S'applique UNIQUEMENT si le cycle a cree/modifie un composant qui appelle une API.

Reference complete : `.claude/rules/frontend-contract-gate.md`

### 3a : Fixture payload reel
```bash
# Capturer depuis le vrai backend
curl -s -H "Authorization: Bearer $TOKEN" https://liascan.tech/api/endpoint > \
  sigma-react-frontend/src/components/**/__fixtures__/{Component}.fixture.json
```
- La fixture DOIT contenir `_captured_from` avec l'URL exacte
- INTERDIT : payload invente ou genere depuis les types TS

### 3b : Render-and-assert test
```tsx
// __tests__/{Component}.test.tsx
import fixture from '../__fixtures__/{Component}.fixture.json';
// Mock fetchWithConfig -> retourne fixture
// Render composant
// Assert : 0 throw, element attendu present, cas erreur 500 sans crash
```

### 3c : Smoke Playwright live
```
Apres deploy : naviguer vers le composant via Playwright
- 0 erreurs console critiques
- Au moins 1 element du composant present dans le DOM
```

### 3d : Service unwrap envelope
```tsx
// INTERDIT
return resp.json();  // sans unwrap

// OBLIGATOIRE
const json = await resp.json();
return (json && typeof json === 'object' && 'data' in json) ? json.data : json;
```

**Verdict R17 : un seul FAIL dans 3a-3d = BLOQUANT, cycle ne se ferme pas.**

---

## Etape 4 : REGRESSION

Comparer les scores avec le cycle/session precedent(e).

### Pour PDCA
```
Charger pdca/{perimetre}/cycle_{N-1}/C_SCORECARD.json
Pour chaque domaine :
  delta = score_actuel - score_precedent
  Si delta < -5 : REGRESSION DETECTEE
```

### Pour APEX
```
Charger dernier RETEX_APEX_*.md du meme domaine
Comparer :
  - Nombre de critiques : doit etre <= precedent
  - Score agentique : doit etre >= precedent
  - Aucun finding CRITIQUE qui etait PASS dans la session precedente
```

### Politique regression
- **Zero tolerance** : aucun domaine ne peut regresser de plus de 5 points
- Si regression detectee : identifier la cause, corriger, re-scorer
- La regression est tracee dans `decision_log.jsonl`
- Le RETEX DOIT mentionner toute regression et son analyse
