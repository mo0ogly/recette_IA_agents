# Build Pipeline React -- Reference partagee APEX & PDCA v6.0

> Pipeline obligatoire pour chaque composant React cree ou modifie.
> Integre : frontend-design 9 gates, react-recette checks, R17 Contract Gate.

---

## Pipeline sequentiel (chaque fichier .tsx/.ts)

```
EDIT/WRITE .tsx/.ts
    |
    v
GATE 1: BUILD
    |-- cd sigma-react-frontend && node node_modules/.bin/vite build
    |-- Zero erreurs TS = PASS
    |-- FAIL -> STOP, corriger
    |
    v
GATE 2: IMPORT
    |-- @mui/material : imports directs (Button from '@mui/material/Button')
    |-- fetchWithConfig depuis '../config/apiConfig' (JAMAIS fetch() brut)
    |-- customLogger depuis '../services/loggerService' (JAMAIS console.log)
    |-- useTheme depuis '@mui/material/styles'
    |
    v
GATE 3: THEME
    |-- Pas de couleurs hex hardcodees -> theme.palette.*
    |-- Pas de fontFamily hardcode -> fontFamily: 'inherit'
    |-- Pas de common.white/common.black -> text.primary, background.paper
    |
    v
GATE 4: LOGGER
    |-- Zero console.log/warn/error/info
    |-- customLogger.info/warn/error partout
    |
    v
GATE 5: CHIP
    |-- borderRadius: 1 (4px) sur tous les Chip MUI
    |-- JAMAIS de badges ovales
    |
    v
GATE 6: HELP (BLOQUANT)
    |-- TOUT composant *Tab.tsx, *Panel.tsx, *Dashboard.tsx, *Editor.tsx, *Manager.tsx, *Status.tsx :
    |-- 1. INSERT INTO ui_help_content (...) AVANT d'ajouter le HelpButton
    |-- 2. Verifier : psql "SELECT 1 FROM ui_help_content WHERE component='xxx' AND tab_key='yyy'"
    |-- 3. <HelpButton component="xxx" tabKey="yyy" /> dans le composant
    |-- component + tabKey (PAS helpId)
    |-- FAIL si HelpButton sans contenu DB = PLACEHOLDER INTERDIT (R4)
    |-- FAIL si composant cree sans HelpButton = GATE NON PASSE
    |
    v
GATE 7: TEST
    |-- cd sigma-react-frontend && npx vitest run
    |-- Tests existants ne cassent pas
    |-- Si nouveau composant : creer test render basique
    |
    v
GATE 8: RUNTIME CRASH
    |-- mcp__playwright__browser_navigate -> page cible
    |-- mcp__playwright__browser_snapshot -> chercher :
    |   "Component Error", "is not a function", "Cannot read properties"
    |-- Chaque .map() sur propriete API DOIT avoir guard || []
    |-- FAIL -> STOP, corriger
    |
    v
GATE 9: INTEGRATION (new files only)
    |-- Si le fichier est NOUVEAU (pas une modification) :
    |-- Verifier que le composant est importe par au moins 1 parent
    |-- Check : grep -rn "import.*ComponentName" src/ --include="*.tsx" --include="*.ts" | grep -v "ComponentName.tsx" | wc -l
    |-- SI 0 imports -> FAIL : composant orphelin (cree mais jamais rendu)
    |-- Cause : un fichier non importe compile mais n'est jamais visible dans l'UI
    |-- Action : importer et rendre dans le composant parent adequat
    |-- Exemples de parents : App.tsx, categories.tsx (CVE Explorer), Dashboard tabs
    |-- FAIL -> STOP, integrer avant de continuer
    |
    v
ALL 9 GATES PASSED -> fichier pret pour phase RECETTE
```

---

## Regles de construction React (conventions AgentRail)

### MUI v7 Grid (CRITIQUE)
```tsx
// CORRECT
<Grid size={{ xs: 12, md: 8 }}>

// INTERDIT
<Grid item xs={12} md={8}>
```

### fetchWithConfig (CRITIQUE)
```tsx
// CORRECT
import { fetchWithConfig } from '../config/apiConfig';
const response = await fetchWithConfig('/api/endpoint');

// INTERDIT
const response = await fetch(url);
const response = await fetch(`${API_BASE_URL}/api/endpoint`);
```

### ConfigurationService (pour URLs)
```tsx
// CORRECT (downloads, websocket)
import { getBackendUrl } from '../../services/ConfigurationService';
const url = `${getBackendUrl()}/api/download/file`;

// INTERDIT
const API_BASE = 'http://localhost:8081';
```

### Couleurs theme-aware
```tsx
// CORRECT
color: theme.palette.error.main
backgroundColor: alpha(theme.palette.warning.main, 0.15)

// INTERDIT
color: '#ff0000'
backgroundColor: 'rgba(255, 165, 0, 0.15)'
```

### Logger
```tsx
// CORRECT
import { customLogger } from '../../services/loggerService';
customLogger.info('COMPONENT', 'message', { data });

// INTERDIT
console.log('debug:', data);
```

### Null safety (incident 2026-04-06)
```tsx
// CORRECT
{(data.items || []).map(item => ...)}
{data?.providers?.length > 0 && ...}

// INTERDIT (crash si items undefined/null)
{data.items.map(item => ...)}
```

### Design (frontend-design integre)

Avant de coder, choisir une direction esthetique :
- **Purpose** : quel probleme l'interface resout ?
- **Tone** : minimal, maximalist, retro, industrial, luxury...
- **Differentiation** : qu'est-ce qui rend ce composant memorable ?

JAMAIS : design generique AI (Inter, Roboto, purple gradient on white, cookie-cutter layout).
TOUJOURS : theme-aware, les themes AgentRail definissent les polices dans `*Theme.tsx`.

### Performance Vercel (top critiques)

```tsx
// CRITIQUE : imports directs MUI (pas barrel)
import Button from '@mui/material/Button';        // CORRECT
import { Button } from '@mui/material';            // INTERDIT

// CRITIQUE : Promise.all pour fetch independants
const [a, b] = await Promise.all([fetch1(), fetch2()]);  // CORRECT
const a = await fetch1(); const b = await fetch2();       // INTERDIT
```

---

## Score pipeline React /8

| Gate | Points | Quand 1 point |
|------|--------|---------------|
| BUILD (vite build) | /1 | exit 0 |
| IMPORT (directs, fetchWithConfig, customLogger) | /1 | 0 violation |
| THEME (pas de hex hardcode) | /1 | 0 violation |
| LOGGER (zero console.*) | /1 | 0 violation |
| CHIP (borderRadius: 1) | /1 | 0 violation |
| HELP (HelpButton present si dashboard) | /1 | present ou N/A |
| TEST (vitest passe) | /1 | exit 0 |
| RUNTIME (Playwright 0 crash) | /1 | 0 Component Error |
