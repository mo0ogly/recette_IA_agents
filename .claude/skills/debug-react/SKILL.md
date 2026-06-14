---
name: debug-react
description: Diagnostic et resolution systematique de bugs React/TypeScript dans LIA-SEC. Se declenche quand un build Vite/TS echoue, un composant ne s'affiche pas, une erreur runtime apparait dans la console, un appel API echoue (401/500), ou quand l'utilisateur demande de debugger du code React/TypeScript. Couvre les 314 composants, 93 services, MUI v7, et fetchWithConfig.
---

# Debug React/TypeScript v3.0 - LIA-SEC

Methodologie systematique pour diagnostiquer et corriger les bugs React/TypeScript dans LIA-SEC.
Principe : **PAS DE FIX SANS ROOT CAUSE D'ABORD.**

---

## Architecture Multi-Agent

| Etape | Role | Responsabilite |
|-------|------|----------------|
| Reproduire le symptome | COLLECTOR | Collecter erreurs build, console, network tab, logs backend |
| Isoler la cause racine | ANALYST | Categoriser, croiser symptomes, identifier le fichier/ligne |
| Planifier le fix | PLANNER | Choisir la strategie de correction (minimal, cible) |
| Appliquer le fix | EXECUTOR | Editer le code, respecter conventions LIA-SEC |
| Valider et documenter | LIBRARIAN | Build gate, anti-pattern check, decision log |

---

## Quality Hooks

| Hook | Declenchement | Action |
|------|---------------|--------|
| **PRE-FIX** | Avant toute modification | Verifier que la root cause est identifiee (pas de fix a l'aveugle) |
| **POST-FIX** | Apres chaque modification | `npx tsc --noEmit` + `npm run build` doivent passer |
| **ANTI-PATTERN** | Apres chaque edit | grep fetch brut, console.log, Grid item, localhost hardcode, emoji |
| **REGRESSION** | Avant de declarer "resolu" | Verifier que le fix n'a pas casse d'autres composants |

---

## Niveaux d'Autonomie

| Niveau | Condition | Comportement |
|--------|-----------|-------------|
| **AUTO** | Erreur de build TS, import casse, type manquant | Fix direct sans demander |
| **SEMI** | Modification de logique metier, refactor composant | Annoncer le plan, executer apres accord implicite |
| **MANUAL** | Suppression de code, changement d'architecture | Demander validation explicite avant d'agir |

---

## Declenchement

- Build TypeScript/Vite echoue (`npm run build`, `npx tsc`)
- Composant ne s'affiche pas ou crash a runtime
- Erreur dans la console navigateur
- Appel API echoue (401 Unauthorized, 500 Internal Server Error)
- L'utilisateur demande "debug", "pourquoi ca s'affiche pas", "fix ce bug React"
- Erreur MUI, theming, ou layout casse

## Phase 1 : REPRODUIRE (COLLECTOR)

### Collecter l'erreur complete
```bash
# Build errors TypeScript
cd sigma-react-frontend && npm run build 2>&1

# Type check sans build
npx tsc --noEmit 2>&1

# Erreur a runtime -> console navigateur (MCP Playwright ou Chromium)
# Lancer les services d'abord
./cleanup_services.sh both
```

### Categoriser l'erreur

| Categorie | Symptomes | Outils |
|-----------|-----------|--------|
| **Build/Compile** | TS errors, import not found, type mismatch | `npx tsc --noEmit` |
| **Runtime** | White screen, console error, crash composant | Console navigateur, Error Boundary |
| **API** | 401, 403, 500, CORS, timeout | Network tab, backend logs |
| **Layout/UI** | Overflow, z-index, composant invisible | DevTools Elements, Playwright screenshot |
| **State** | Donnees pas a jour, infinite re-render, stale closure | React DevTools, console.log temporaire |

### Questions a se poser
1. **Quand** ca a commence ? (`git log --oneline -10 -- sigma-react-frontend/`)
2. **Ou** exactement ? (quel composant, quel route, quel onglet)
3. **Quoi** a change ? (`git diff HEAD~3 -- sigma-react-frontend/`)
4. **Console** : quel est le message exact ?

## Phase 2 : ISOLER (ANALYST)

### Erreurs de build TypeScript

```bash
# Obtenir TOUTES les erreurs
npx tsc --noEmit 2>&1 | head -50

# Compter les erreurs
npx tsc --noEmit 2>&1 | grep "error TS" | wc -l

# Erreur specifique a un fichier
npx tsc --noEmit 2>&1 | grep "MonComposant"
```

**Patterns frequents :**

| Erreur TS | Cause | Fix |
|-----------|-------|-----|
| `TS2307: Cannot find module` | Import casse, fichier deplace | Verifier le chemin avec Glob |
| `TS2339: Property does not exist` | Type manquant ou interface incomplete | Ajouter le champ a l'interface |
| `TS2345: Argument not assignable` | Type incompatible | Verifier la signature de la fonction |
| `TS7006: Parameter implicitly has 'any'` | Type manquant | Ajouter le type explicite |
| `TS18048: X is possibly undefined` | Null check manquant | Ajouter `?.` ou `if (x)` |

### Erreurs runtime React

**White screen (crash complet) :**
1. Ouvrir la console navigateur (F12 ou MCP)
2. L'erreur indique quel composant crash
3. Chercher le composant : `Glob **/*NomComposant*.tsx`
4. Verifier : imports, props undefined, hooks mal places

**Composant ne s'affiche pas :**
1. Verifier le routing (est-ce que la route existe dans App.tsx / sidebar ?)
2. Verifier les conditions de rendu (`{condition && <Composant />}`)
3. Verifier le z-index et overflow (voir `sigma-react-frontend/CLAUDE.md`)

**Infinite re-render :**
1. Chercher les `useEffect` sans dependencies correctes
2. Chercher les objets/arrays recrees a chaque render dans les deps
3. Verifier les `setState` dans les `useEffect` (boucle)

### Erreurs API (401, 500, CORS)

**401 Unauthorized :**
```
CAUSE PROBABLE : fetch() brut au lieu de fetchWithConfig()
```
```typescript
// INTERDIT -> 401 systematique sur endpoints proteges
const response = await fetch('/api/endpoint');

// CORRECT -> fetchWithConfig injecte le Bearer token
import { fetchWithConfig } from '../config/apiConfig';
const response = await fetchWithConfig('/api/endpoint');
```

Verifier aussi : le endpoint est-il dans `publicRoutes` (backend `auth_session_middleware.go`) ?

**500 Internal Server Error :**
1. Verifier les logs backend : `./cleanup_services.sh status` puis `tail -50 /tmp/lia_backend.log`
2. Le bug est probablement cote Go, pas React -> utiliser `/debug-go`

**CORS error :**
1. Verifier le proxy dans `sigma-react-frontend/package.json` (`"proxy": "http://localhost:8081"`)
2. Verifier les headers CORS dans le backend Go

### Erreurs MUI v7

| Erreur | Cause | Fix |
|--------|-------|-----|
| Warning: Grid item | Ancienne syntaxe MUI v5/v6 | `<Grid size={{ xs: 12, md: 8 }}>` |
| Theme non applique | ThemeProvider manquant ou mauvais import | Verifier le wrapper |
| Composant invisible | z-index ou overflow hidden | Voir `sigma-react-frontend/CLAUDE.md` |

## Phase 3 : CORRIGER (PLANNER + EXECUTOR)

### Regles de correction LIA-SEC
1. **Fix minimal** : toucher le moins de fichiers possible
2. **Corriger LA CAUSE, pas le symptome**
3. **Conventions obligatoires** :
   - `fetchWithConfig()` : JAMAIS `fetch()` brut
   - `customLogger.info()` : JAMAIS `console.log()`
   - `getBackendUrl()` via ConfigurationService : JAMAIS `http://localhost:8081`
   - MUI v7 : `<Grid size={{ xs: 12 }}>`, JAMAIS `<Grid item xs={12}>`
   - Zero emoji dans l'UI
4. **Imports** : ordre = react, libs externes, composants, services, utils, types

### Fix applique -> Gate obligatoire
```bash
# Type check
cd sigma-react-frontend && npx tsc --noEmit

# Build complet
npm run build

# Si composant impacte -> react-recette
# /react-recette sur le composant modifie
```

## Phase 4 : VALIDER (LIBRARIAN)

1. **Build passe** : `npm run build` sans erreur
2. **UI fonctionne** : tester visuellement (Playwright MCP si dispo)
3. **Pas de regression** : les autres composants marchent encore
4. **Diff propre** : pas de console.log, TODO, placeholder, debug residuel
5. **Anti-patterns verifies** :
   - Pas de `fetch()` brut
   - Pas de `console.log()`
   - Pas de `http://localhost`
   - Pas de `<Grid item xs=`
   - Zero emoji

## Adaptation et Replanification

- **2 echecs consecutifs sur le meme fix** -> INVOQUER `/replan` immediatement
- **Ne JAMAIS improviser** : si le pattern n'est pas dans ce skill, chercher dans `sigma-react-frontend/CLAUDE.md` ou `.claude/rules/anti-patterns.md`
- **Escalade structuree** : apres 3 tentatives sans resultat, documenter ce qui a ete essaye et changer de strategie (isolation composant, bisect git, test minimal)

## Commandes utiles

```bash
# Build
cd sigma-react-frontend && npm run build 2>&1

# Type check rapide
npx tsc --noEmit 2>&1 | head -30

# Trouver un composant
find sigma-react-frontend/src -name "*Dashboard*" -type f

# Chercher les fetch() bruts (anti-pattern)
grep -rn "await fetch(" sigma-react-frontend/src/ --include="*.tsx" --include="*.ts" | grep -v "fetchWithConfig" | grep -v "node_modules"

# Chercher les console.log oublies
grep -rn "console\.\(log\|warn\|error\)" sigma-react-frontend/src/ --include="*.tsx" --include="*.ts" | grep -v "customLogger" | grep -v "node_modules"

# Chercher les Grid MUI v5/v6
grep -rn "Grid item" sigma-react-frontend/src/ --include="*.tsx"

# Chercher les localhost hardcodes
grep -rn "localhost:8081" sigma-react-frontend/src/ --include="*.tsx" --include="*.ts"

# Lister les fichiers modifies recemment
git log --oneline --name-only --diff-filter=M -- 'sigma-react-frontend/src/' | head -30

# Piping erreurs vers Claude
npm run build 2>&1 | tail -50
```

## Integration avec d'autres skills

| Situation | Skill a chainer |
|-----------|----------------|
| Bug API 500 (backend Go) | `/debug-go` |
| Composant modifie a valider | `/react-recette` |
| Nouveau composant a creer | `/apex -t` |
| Bug UI visible (screenshot) | `/webapp-testing` |

## Escalade

Si apres 3 tentatives le bug n'est pas resolu :
1. Documenter ce qui a ete essaye
2. Verifier le `sigma-react-frontend/CLAUDE.md` pour des contraintes oubliees
3. Chercher si c'est un bug MUI connu (WebSearch agent)
4. Tester en isolation : creer un composant minimal qui reproduit le bug
5. Verifier les versions : `npm list @mui/material react typescript`

---

## Tracabilite Agentique (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_DEBUG_REACT_{ID}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"debug-react-{ID}","action":"ROOT_CAUSE_IDENTIFIED","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_DEBUG_REACT_{ID}"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

### Action journal
A chaque phase, consigner dans le plan : action effectuee, resultat observe, decision prise.

---

## Scoring Agentique (/50)

| Critere | Points | Description |
|---------|--------|-------------|
| **C1 Decomposition** | /10 | Erreur correctement categorisee, root cause isolee avant fix |
| **C2 Planification** | /10 | Fix minimal identifie, fichiers cibles listes, pas de shotgun debug |
| **C3 Replanification** | /10 | Adaptation apres echec (2 fails -> /replan), pas d'acharnement |
| **C4 Outillage dynamique** | /10 | Bons outils utilises (tsc, grep, Playwright, git bisect) |
| **C5 Tracabilite** | /10 | Decision log rempli, plan mis a jour, anti-patterns verifies |
| **TOTAL** | **/50** | |
