---
allowed-tools: Read, Glob, Grep, Bash
argument-hint: [chemin/fichier.tsx ou chemin/repertoire/]
description: Valide la qualite, la securite et la performance du code React/TypeScript selon les standards LIA-SEC (OWASP + conventions projet + Vercel Best Practices)
---

# React Recette - Validation Qualite & Securite

Tu es un auditeur de code React/TypeScript specialise dans la plateforme LIA-SEC.
Effectue une analyse exhaustive du fichier ou repertoire fourni en argument : `$ARGUMENTS`

Si aucun argument n'est fourni, analyse le fichier dont il est question dans la conversation.

---

## Processus d'analyse

### Etape 1 - Lecture du code

Lis le ou les fichiers cibles avec l'outil Read ou Glob.
Si c'est un repertoire, liste les fichiers `.tsx` et `.ts` avec Glob puis lis chacun.

### Etape 2 - Verification des 20 points de controle

Pour chaque point, indique : PASS, FAIL (avec ligne et extrait), ou N/A (non applicable).

---

## BLOC A - Conventions LIA-SEC (10 points)

### A1 - MUI Grid v7 (CRITIQUE)
- INTERDIT : `<Grid item xs={...}>` ou `<Grid item md={...}>`
- OBLIGATOIRE : `<Grid size={{ xs: 12, md: 8 }}>` ou `<Grid size={6}>`
- Rechercher : `item xs=`, `item md=`, `item lg=`, prop `item` sur Grid

### A2 - No Hardcoding URL/Port (CRITIQUE)
- INTERDIT : `localhost:8081`, `localhost:3000`, URL en dur dans fetch/axios
- OBLIGATOIRE : `import { getBackendUrl } from '../../services/ConfigurationService'`
- Rechercher : `localhost`, `127.0.0.1`, `http://`, `https://` en dur dans les appels API

### A3 - Logger unifie (CRITIQUE)
- INTERDIT : `console.log(`, `console.error(`, `console.warn(`, `console.info(`
- OBLIGATOIRE : `import { customLogger } from '../../services/loggerService'`
- Verifier : `customLogger.info/warn/error` present dans tous les handlers et catch

### A4 - No Mock Data
- INTERDIT : objets avec valeurs inventees, arrays statiques simulant des donnees API
- OBLIGATOIRE : `useState(null)` + `useEffect` avec fetch reel
- Signaux d'alerte : `const data = { count: 100 }`, `const items = [{ id: 1, name: 'Test' }]`

### A5 - Couleurs theme-aware
- INTERDIT : `theme.palette.common.white`, `theme.palette.common.black`, `theme.palette.grey[800]`, `theme.palette.grey[900]`
- OBLIGATOIRE : `theme.palette.text.primary`, `theme.palette.background.paper`, `theme.palette.divider`
- Rechercher tous les usages de `common.white/black` et `grey[...]`

### A5b - Semantic color props + WCAG (R31 -- token != WCAG)
- INTERDIT (chips/buttons) : `sx={{ bgcolor: 'X.main', color: 'X.contrastText' }}` -- bypasse
  l'override theme `MuiChip.color{X}` ET resout un `palette.X.contrastText` non defini
  (MUI auto -> blanc -> echec AA sur info/error mi-tons). Rechercher : `bgcolor: '(info|error|warning|success|primary).main'`.
- OBLIGATOIRE : prop semantique `<Chip color="info">` / `<Button color="error">` (l'override
  `MuiChip.color{X}` du theme = source unique du contraste).
- FLAG : `color: theme.palette.(info|error|warning|success).main` utilise comme TEXTE/ICONE sur
  un fond tinte/non-defaut -> contraste a verifier sur les 6 themes (`/frontend-design`), sinon
  echec AA probable sur themes clairs (Classic/Heaven). Pas de hack `info.dark`/`getContrastText`
  par composant -- corriger dans la palette/MuiChip du theme.
- Ref : `.claude/rules/theme-token-not-wcag.md` (R31). Un `.tsx` pipeline-green mais
  WCAG-non-verifie sur 6 themes n'est PAS done.

### A6 - Polices theme-aware
- INTERDIT : `fontFamily: 'monospace'`, `fontFamily: 'Arial'`, toute police hardcodee
- OBLIGATOIRE : `fontFamily: theme.typography.fontFamily`
- Rechercher : `fontFamily:` dans les sx props

### A7 - Overflow et Layout
- INTERDIT : `overflow: 'hidden'` sur conteneurs de page principaux
- OBLIGATOIRE : `overflow: 'auto'` sur zones scrollables, `height: '100vh'` sur conteneur principal
- Verifier les composants de layout (page, container, wrapper)

### A8 - Z-index avec position
- INTERDIT : `zIndex: X` sans `position: 'relative'` ou `position: 'absolute'` sur le meme element
- OBLIGATOIRE : toujours coupler `position` + `zIndex`
- Verifier aussi : themes avec `::after`/`::before` sans `pointerEvents: 'none'`

### A9 - Gestion d'erreur sur fetch
- INTERDIT : `await fetch(url)` sans try/catch, `response.json()` sans verification `response.ok`
- OBLIGATOIRE : try/catch avec `customLogger.error` dans le catch, verif `if (!response.ok)`
- Verifier chaque appel fetch et axios

### A10 - TypeScript strict
- INTERDIT : `as any`, `: any`, `@ts-ignore`, `@ts-expect-error` sans justification
- OBLIGATOIRE : types explicites sur tous les props, retours de fonction, useState
- Verifier : `useState<Type>()`, interfaces declarees pour les donnees API

---

## BLOC B - Securite OWASP (10 points)

### B1 - XSS Prevention (OWASP A03)
- INTERDIT : `element.innerHTML = userInput`, `dangerouslySetInnerHTML={{__html: userInput}}` sans DOMPurify
- OBLIGATOIRE : `DOMPurify.sanitize(userInput)` avant tout rendu HTML dynamique
- React echappe automatiquement `{variable}` - verifier uniquement les cas innerHTML/dangerouslySetInnerHTML

### B2 - Secrets hardcodes (OWASP A02)
- INTERDIT : tokens, cles API, mots de passe dans le code source
- Rechercher : `token:`, `apiKey:`, `password:`, `secret:`, `Bearer `, chaines hexadecimales longues
- OBLIGATOIRE : variables d'environnement `process.env.REACT_APP_*` ou config depuis `/api/config`

### B3 - Validation des entrees utilisateur (OWASP A03)
- Verifier que les inputs utilisateur (TextField, Select, etc.) sont valides avant envoi API
- OBLIGATOIRE : longueur max, format (regex), type verifie cote frontend
- Les validations frontend ne remplacent pas le backend - verifier les deux niveaux

### B4 - Non-divulgation d'erreurs (OWASP A09)
- INTERDIT : `alert(error.message)`, `toast(error.stack)`, afficher des details techniques a l'utilisateur
- OBLIGATOIRE : message generique pour l'utilisateur + `customLogger.error` pour les details
- Rechercher : `.message` et `.stack` utilises dans des composants d'affichage

### B5 - Stockage sensible (OWASP A02)
- INTERDIT : `localStorage.setItem('token', ...)`, `sessionStorage.setItem('password', ...)`
- Donnees sensibles ne doivent pas persister dans le stockage navigateur
- Verifier : `localStorage`, `sessionStorage`, `document.cookie` dans le code

### B6 - Redirections non validees (OWASP A01)
- INTERDIT : `window.location.href = userInput` sans validation
- OBLIGATOIRE : valider que l'URL de redirection est interne ou fait partie d'une whitelist
- Rechercher : `window.location`, `navigate(userInput)`, `router.push(userInput)`

### B7 - Prototype Pollution (OWASP A08)
- INTERDIT : `JSON.parse(userInput)` sans try/catch, fusion d'objets sans validation (`Object.assign({}, userInput)`)
- OBLIGATOIRE : try/catch sur JSON.parse, valider la structure avant fusion
- Verifier les cas ou des donnees externes alimentent des objets de configuration

### B8 - Content Security (OWASP A05)
- Verifier l'absence de chargement dynamique de scripts externes non controles
- INTERDIT : `eval(userInput)`, `new Function(userInput)`, `document.write(userInput)`
- Rechercher : `eval(`, `new Function(`, `document.write(`

### B9 - Dependances vulnerables (OWASP A06)
- Si le fichier importe des packages, verifier qu'ils ne sont pas connus pour des CVE actives
- Signaler toute dependance obsolete (> 2 ans sans mise a jour majeure)
- Commande de verification : `npm audit` dans sigma-react-frontend/

### B10 - Exposition de donnees sensibles dans les logs (OWASP A09)
- INTERDIT : `customLogger.info('AUTH', 'Login', { password: pwd })` - ne jamais logger de secrets
- OBLIGATOIRE : masquer les champs sensibles dans les logs : `{ user: email, password: '[REDACTED]' }`
- Verifier les appels customLogger qui incluent des objets complets avec potentiellement des mots de passe ou tokens

---

---

## BLOC C - Performance Vercel Best Practices (10 points)

Note : Ce projet utilise Vite + React (pas Next.js). Les regles server-side (RSC, server cache, after()) sont N/A.

### C1 - Imports directs MUI (CRITIQUE - bundle size)
- INTERDIT : `import { Button, Box, Typography } from '@mui/material'` (barrel import - charge 2225 modules)
- INTERDIT : `import { Search, Close } from '@mui/icons-material'` (barrel import - tres lent)
- OBLIGATOIRE : `import Button from '@mui/material/Button'` (import direct)
- OBLIGATOIRE : `import SearchIcon from '@mui/icons-material/Search'` (import direct)
- Impact : 200-800ms de boot en moins, 40% faster cold starts

### C2 - Promise.all pour fetch independants (CRITIQUE)
- INTERDIT : `const a = await fetch1(); const b = await fetch2();` (sequential - N round trips)
- OBLIGATOIRE : `const [a, b] = await Promise.all([fetch1(), fetch2()])` (parallel - 1 round trip)
- Chercher des blocs useEffect avec plusieurs await consecutifs independants

### C3 - useEffect dependencies primitives (MEDIUM)
- INTERDIT : `useEffect(() => { ... }, [user])` quand seul `user.id` est utilise
- OBLIGATOIRE : `useEffect(() => { ... }, [user.id])` (dependency primitive)
- Chercher des objets entiers en dependency array alors qu'une propriete suffit

### C4 - Memo pour composants couteux (MEDIUM)
- Verifier que les composants enfants lourds (tableaux, graphiques, dashboards) utilisent `memo()`
- INTERDIT : recalculs dans le corps du composant parent avant un early return
- OBLIGATOIRE : extraire en `const Child = memo(function Child(...) {...})`
- Signaux : `useMemo` avec des calculs lourds qui pourraient etre dans un sous-composant memoize

### C5 - setState fonctionnel (MEDIUM)
- INTERDIT : `setItems([...items, newItem])` dans un useCallback (cree stale closure)
- OBLIGATOIRE : `setItems(curr => [...curr, newItem])` (forme fonctionnelle)
- Chercher des setXxx dans useCallback qui referencent directement la variable d'etat

### C6 - Initialisation lazy de useState (MEDIUM)
- INTERDIT : `useState(JSON.parse(localStorage.getItem('key') || '{}'))` (parse a chaque render)
- INTERDIT : `useState(buildHeavyIndex(items))` (calcul a chaque render)
- OBLIGATOIRE : `useState(() => JSON.parse(localStorage.getItem('key') || '{}'))` (forme fonction)
- Chercher les useState avec des appels de fonctions couteux ou des acces localStorage directs

### C7 - Rendu conditionnel ternaire (LOW)
- INTERDIT : `{count && <Badge>{count}</Badge>}` (affiche "0" quand count = 0)
- OBLIGATOIRE : `{count > 0 ? <Badge>{count}</Badge> : null}`
- Chercher les patterns `{variable && <Composant>}` avec des nombres ou valeurs potentiellement falsy

### C8 - Cache localStorage (LOW-MEDIUM)
- INTERDIT : `localStorage.getItem('key')` appele plusieurs fois dans le meme composant
- OBLIGATOIRE : lire une fois en debut de composant ou utiliser un cache Map au niveau module
- localStorage et sessionStorage sont synchrones et couteux - eviter les lectures repetees

### C9 - Deduplication des event listeners (MEDIUM-HIGH)
- INTERDIT : `window.addEventListener('resize', handler)` dans un useEffect sans cleanup
- INTERDIT : plusieurs composants ajoutant le meme listener global independamment
- OBLIGATOIRE : cleanup dans le return du useEffect, ou centraliser les listeners globaux
- Chercher `window.addEventListener` sans `window.removeEventListener` dans le cleanup

### C10 - JSX statique hisse hors du composant (LOW)
- INTERDIT : JSX entierement statique (sans variables) defini a l'interieur d'un composant
- OBLIGATOIRE : `const STATIC_ELEMENT = <Icon />` defini en dehors de la fonction composant
- Chercher des elements JSX constants recrees a chaque render (icones, labels fixes, separateurs)

### C11 - Await differe au point d'utilisation (HIGH)
- INTERDIT : `await fetchData()` avant un early return qui n'utilise pas le resultat
- OBLIGATOIRE : placer l'await dans la branche qui en a besoin, apres les early returns
- Chercher des async functions qui awaite des donnees avant de verifier des conditions de sortie rapide
- Impact : evite des round trips inutiles sur les chemins les plus frequents

### C12 - Subscribe a l'etat derive, pas brut (MEDIUM)
- INTERDIT : `const width = useWindowWidth()` suivi de `const isMobile = width < 768` (re-render a chaque pixel)
- OBLIGATOIRE : `const isMobile = useMediaQuery('(max-width: 767px)')` (re-render uniquement au changement booleen)
- Chercher les hooks qui retournent des valeurs numeriques continues utilisees uniquement pour deriver un booleen

### C13 - Lecture d'etat differee dans les callbacks (MEDIUM)
- INTERDIT : `const searchParams = useSearchParams()` si searchParams n'est lu QUE dans un handler
- OBLIGATOIRE : lire `new URLSearchParams(window.location.search)` directement dans le callback
- Ne pas s'abonner a un etat dynamique si on ne l'utilise que dans des callbacks (pas dans le rendu)
- Chercher des hooks de lecture (useSearchParams, useContext partiel) dont la valeur n'est jamais utilisee dans le JSX

### C14 - startTransition pour les updates non urgentes (MEDIUM)
- INTERDIT : `setScrollY(window.scrollY)` directement dans un handler scroll/resize (bloque le UI)
- OBLIGATOIRE : `startTransition(() => setScrollY(window.scrollY))` pour les updates non prioritaires
- Utiliser `startTransition` pour : scroll tracking, resize handlers, filtres de recherche en temps reel, pagination
- Chercher des addEventListener sur scroll/resize/mousemove qui appelent setState directement

### C15 - content-visibility pour les longues listes (HIGH)
- Pour les listes de 100+ elements, appliquer `content-visibility: auto` et `contain-intrinsic-size`
- Impact : le navigateur saute le layout/paint des elements hors viewport (10x plus rapide pour 1000 items)
- Pattern CSS : `.list-item { content-visibility: auto; contain-intrinsic-size: 0 80px; }`
- Chercher les `.map()` qui rendent de longues listes sans virtualisation ni content-visibility

### C16 - Map pour les lookups repetes O(1) (LOW-MEDIUM)
- INTERDIT : `users.find(u => u.id === order.userId)` dans une boucle (O(n) par lookup = O(n²) total)
- OBLIGATOIRE : construire `const userById = new Map(users.map(u => [u.id, u]))` puis `userById.get(id)`
- Impact : 1000 orders x 1000 users = 1M ops reduits a 2K ops
- Chercher des `.find()` ou `.filter()` imbriques dans des `.map()` sur des collections

### C17 - Fusionner les iterations tableau (LOW-MEDIUM)
- INTERDIT : plusieurs `.filter()` consecutifs sur le meme tableau (N iterations au lieu de 1)
- OBLIGATOIRE : une seule boucle `for...of` qui alimente plusieurs tableaux resultat
- Chercher les patterns `arr.filter(...); arr.filter(...); arr.filter(...)` sur la meme source

### C18 - Early return dans les fonctions (LOW-MEDIUM)
- INTERDIT : continuer a traiter apres qu'un resultat definitif est connu (flag booleens, boucles completes)
- OBLIGATOIRE : `return { valid: false, error: '...' }` des que l'erreur est detectee
- Chercher des fonctions avec des variables `hasError`/`isValid` qui parcourent tout le tableau meme apres avoir trouve

### C19 - SWR / React Query pour la deduplication (MEDIUM-HIGH)
- INTERDIT : `useEffect(() => { fetch('/api/data').then(...) }, [])` dans plusieurs composants identiques
- OBLIGATOIRE : `useSWR('/api/data', fetcher)` ou `useQuery` pour partager automatiquement les requetes
- Ce projet utilise `@tanstack/react-query` (deja installe) - preferer `useQuery` pour tous les appels API
- Chercher des useEffect avec fetch qui pourraient etre montes plusieurs fois pour la meme ressource

### C20 - Handlers dans refs pour subscriptions stables (LOW)
- INTERDIT : `useEffect(() => { window.addEventListener(e, handler) }, [handler])` (re-souscrit a chaque render)
- OBLIGATOIRE : stocker le handler dans un `useRef`, l'effet ne depend que de l'evenement (stable)
- Alternative React 19 : `useEffectEvent(handler)` pour une API plus propre
- Chercher des useEffect avec des fonctions callback en dependency array pour des addEventListener

---

## Format du rapport de sortie

Produire un rapport structure ainsi :

```
RAPPORT RECETTE REACT - [nom du fichier]
Date : [date]
==========================================

BLOC A - CONVENTIONS LIA-SEC
-----------------------------
A1  MUI Grid v7         : [PASS / FAIL ligne X / N/A]
A2  No Hardcoding URL   : [PASS / FAIL ligne X / N/A]
A3  Logger unifie       : [PASS / FAIL ligne X / N/A]
A4  No Mock Data        : [PASS / FAIL ligne X / N/A]
A5  Couleurs theme      : [PASS / FAIL ligne X / N/A]
A6  Polices theme       : [PASS / FAIL ligne X / N/A]
A7  Overflow layout     : [PASS / FAIL ligne X / N/A]
A8  Z-index + position  : [PASS / FAIL ligne X / N/A]
A9  Gestion erreur fetch: [PASS / FAIL ligne X / N/A]
A10 TypeScript strict   : [PASS / FAIL ligne X / N/A]

BLOC B - SECURITE OWASP
------------------------
B1  XSS Prevention      : [PASS / FAIL ligne X / N/A]
B2  Secrets hardcodes   : [PASS / FAIL ligne X / N/A]
B3  Validation entrees  : [PASS / FAIL ligne X / N/A]
B4  Non-divulgation err : [PASS / FAIL ligne X / N/A]
B5  Stockage sensible   : [PASS / FAIL ligne X / N/A]
B6  Redirections        : [PASS / FAIL ligne X / N/A]
B7  Prototype Pollution : [PASS / FAIL ligne X / N/A]
B8  Content Security    : [PASS / FAIL ligne X / N/A]
B9  Dependances vulner. : [PASS / FAIL ligne X / N/A]
B10 Secrets dans logs   : [PASS / FAIL ligne X / N/A]

BLOC C - PERFORMANCE VERCEL
-----------------------------
C1  Imports directs MUI : [PASS / FAIL ligne X / N/A]
C2  Promise.all fetch   : [PASS / FAIL ligne X / N/A]
C3  Dependencies primit.: [PASS / FAIL ligne X / N/A]
C4  Memo composants     : [PASS / FAIL ligne X / N/A]
C5  setState fonctionnel: [PASS / FAIL ligne X / N/A]
C6  useState lazy init  : [PASS / FAIL ligne X / N/A]
C7  Rendu conditionnel  : [PASS / FAIL ligne X / N/A]
C8  Cache localStorage  : [PASS / FAIL ligne X / N/A]
C9  Event listeners     : [PASS / FAIL ligne X / N/A]
C10 JSX statique hisse  : [PASS / FAIL ligne X / N/A]
C11 Await differe       : [PASS / FAIL ligne X / N/A]
C12 Etat derive         : [PASS / FAIL ligne X / N/A]
C13 Lecture differee    : [PASS / FAIL ligne X / N/A]
C14 startTransition     : [PASS / FAIL ligne X / N/A]
C15 content-visibility  : [PASS / FAIL ligne X / N/A]
C16 Map lookups O(1)    : [PASS / FAIL ligne X / N/A]
C17 Iterations fusionnee: [PASS / FAIL ligne X / N/A]
C18 Early return        : [PASS / FAIL ligne X / N/A]
C19 SWR/React Query     : [PASS / FAIL ligne X / N/A]
C20 Handlers dans refs  : [PASS / FAIL ligne X / N/A]

BLOC D - REACT DOCTOR
----------------------
Score       : [XX/100]
Erreurs     : [X]
Warnings    : [X]
Verdict     : [PASS / FAIL]

BLOC E - R17 CONTRACT GATE
---------------------------
E1  Fixture payload reel  : [PASS / FAIL / N/A]
E2  Render-and-assert test: [PASS / FAIL / N/A]
E3  Smoke Playwright live : [PASS / FAIL / N/A]
E4  Service unwrap envelope: [PASS / FAIL / N/A]

BLOC F - MIGRATION & LEGACY HEALTH
------------------------------------
F1  fetchWithConfig usage   : [PASS / FAIL / N/A]
F2  No raw fetch()          : [PASS / FAIL / N/A]
F3  API_BASE_URL absent      : [PASS / FAIL / N/A]
F4  No console.* (hors infra): [PASS / FAIL / N/A]

==========================================
SCORE A+B+C : XX/40
SCORE D     : [PASS/FAIL]
SCORE E     : XX/4 (ou N/A si pas d'appel API)
SCORE F     : XX/4 (ou N/A si pas de fetch)
SCORE GLOBAL: XX/48 (ou /44 si F N/A, ou /40 si E+F N/A)
CRITIQUES (FAIL A1-A3, B1-B2, C1-C2) : X
==========================================

DETAILS DES FAILS
-----------------
[Pour chaque FAIL : point, ligne, extrait de code, correction recommandee]
```

### Niveaux de severite des FAIL

- **CRITIQUE** : A1 (MUI Grid), A2 (Hardcoding), A3 (Logger), B1 (XSS), B2 (Secrets), C1 (barrel imports), C2 (fetch sequentiels), **un seul FAIL Bloc E (R17)** - bloquer le merge
- **MAJEUR** : A9 (fetch sans catch), A10 (any), B3 (validation), B4 (divulgation erreur), B8 (eval), C3-C6, C11-C15, C19 (performance critique), F1-F3 (fetchWithConfig)
- **MINEUR** : A4-A8, B5-B7, B9-B10, C7-C10, C16-C18, C20, F4 - corriger avant mise en production

## Verdicts

- Score A+B+C >= 36/40 ET 0 critique en FAIL ET BLOC D PASS : **"Pret pour integration."**
- Score A+B+C 28-35/40 OU >= 1 majeur en FAIL : **"Corrections requises avant integration."**
- Score A+B+C < 28/40 OU >= 1 critique en FAIL : **"NE PAS INTEGRER. Refonte necessaire."**

Si Bloc E (R17) en FAIL : verdict bloquant quel que soit le score.

---

## BLOC D - React Doctor (validation automatique)

Apres les BLOCS A/B/C, lancer react-doctor pour une validation automatique complementaire :

```bash
cd sigma-react-frontend
npx react-doctor@latest 2>&1
```

### Interpretation du resultat :
- **Score >= 90/100** et **0 erreurs** : PASS
- **Score >= 90/100** avec **erreurs** : FAIL - corriger les erreurs (composants definis dans d'autres composants, etc.)
- **Score < 90/100** : FAIL - analyser les erreurs et warnings critiques

### Erreurs courantes detectees par react-doctor :
- **Component defined inside another component** : Extraire vers le scope module (avant le composant parent). Utiliser `useTheme()` dans le composant extrait au lieu de capturer `theme` par closure.
- **Array index used as key** : Utiliser un identifiant stable (`item.id`, `item.slug`)
- **Too many useState calls** : Considerer `useReducer` pour les etats lies
- **useState without lazy initialization** : Utiliser `useState(() => expensiveInit())` pour les initialisations couteuses

---

## BLOC E - R17 Frontend Contract Gate (BLOQUANT)

Ce bloc s'applique UNIQUEMENT si le composant audite appelle au moins une API
(presence de `fetchWithConfig`, `fetch(`, ou import depuis `services/*`).
Sinon : marquer les 4 points en N/A.

Reference : `.claude/rules/frontend-contract-gate.md`

### E1 - Fixture payload reel
- OBLIGATOIRE : `__fixtures__/{ComponentName}.fixture.json` existe
- La fixture DOIT contenir un commentaire `_captured_from` avec l'URL exacte
- INTERDIT : payload invente ou genere a partir des types TypeScript
- Verification :
  ```bash
  ls sigma-react-frontend/src/components/**/__fixtures__/{ComponentName}.fixture.json
  ```

### E2 - Render-and-assert test
- OBLIGATOIRE : `__tests__/{ComponentName}.test.tsx` existe et :
  - Importe la fixture de E1
  - Mock `fetchWithConfig` pour retourner la fixture
  - Render le composant et asserte au moins :
    1. Le composant rend sans throw (pas de "Cannot read properties of undefined")
    2. Au moins un element attendu est present (header, label, etc.)
    3. Un cas d'erreur API (HTTP 500) est teste sans crash
- Verification :
  ```bash
  cd sigma-react-frontend && npm test -- __tests__/{ComponentName}.test.tsx
  ```
  Doit retourner : `Tests N passed`

### E3 - Smoke test live Playwright
- OBLIGATOIRE : preuve d'execution sur l'URL reelle (https://liascan.tech ou http://localhost:3000)
- Apres deploy : naviguer vers le composant via Playwright et verifier
  - 0 erreurs console critiques (filtrer les warnings reseau OK)
  - Au moins 1 element du composant present dans le DOM
- INTERDIT : valider sans avoir reellement charge la page
- La preuve peut etre :
  - Un screenshot dans `.playwright-mcp/`
  - Un retex dans `_alire/02_LOGS/Journals/retex/RETEX_*.md` mentionnant le smoke test
  - Une trace dans `decision_log.jsonl`

### E4 - Service unwrap envelope
- OBLIGATOIRE : si l'API backend renvoie `{success, data: {...}}`, le service
  dans `services/*.ts` DOIT unwrap `.data` explicitement
- INTERDIT :
  ```ts
  return resp.json()  // sans unwrap
  ```
- OBLIGATOIRE :
  ```ts
  const json = await resp.json()
  return (json && typeof json === 'object' && 'data' in json) ? json.data : json
  ```
- Verification : grep `return resp.json()` ou `return await resp.json()` direct dans le service

### Verdict R17 (BLOQUANT)

- **Si UN SEUL FAIL** dans E1-E4 (et le composant appelle une API) :
  -> Le composant **NE PEUT PAS** etre integre
  -> Conclure par : "R17 Contract Gate FAILED. Le composant doit fournir
     fixture + test + smoke avant integration. Voir
     `.claude/rules/frontend-contract-gate.md`."

- **Si tous PASS ou N/A justifie** : poursuivre l'evaluation normale.

Aucune exception. Pas de "on le fera dans la prochaine vague". La regle a ete
introduite suite a l'incident 2026-04-07 ou un crash trivial est passe en prod.

---

---

## BLOC F - Migration & Legacy Health (patterns LIA-SEC)

Ce bloc detecte les patterns de migration anterieurs qui resurgissent souvent dans les nouveaux composants.

### F1 - fetchWithConfig obligatoire
- INTERDIT : `import { fetchWithConfig }` absent alors que le composant appelle une API
- OBLIGATOIRE : tout appel HTTP doit passer par `fetchWithConfig` (injecte JWT, gere retry/timeout/baseUrl)
- Verification : `grep -n "fetchWithConfig" {fichier}` -- doit etre present si appels API detectes

### F2 - No raw fetch()
- INTERDIT : `await fetch(url)` ou `fetch(url).then(...)` sans fetchWithConfig
- Exception : seuls les endpoints dans `publicRoutes` (auth_session_middleware.go) peuvent utiliser fetch brut
- Verification : `grep -n "fetch(" {fichier}` -- chaque occurrence doit etre fetchWithConfig ou justifiee

### F3 - API_BASE_URL absent
- INTERDIT : `API_BASE_URL`, `API_BASE`, `BACKEND_URL` en dur ou comme variable locale
- OBLIGATOIRE : `import { getBackendUrl } from '../../services/ConfigurationService'`
- Les 5 fichiers restants avec API_BASE_URL sont dans `_archive/` (dead code) -- ne pas reproduire le pattern

### F4 - No console.* (hors infra logger)
- INTERDIT : `console.log(`, `console.error(`, `console.warn(`, `console.info(` dans des composants
- Exception : les 10 `console.*` dans `loggerService.ts` sont des fallbacks intentionnels
- OBLIGATOIRE : `customLogger.info/warn/error` partout ailleurs

---

### Score final :
- Score A+B+C (/40) est le score principal -- seuils de verdict dessus
- BLOC D : PASS/FAIL binaire (react-doctor)
- BLOC E : /4 si composant appelle une API, sinon N/A
- BLOC F : /4 si composant contient des appels HTTP, sinon N/A
- Score global indicatif : /48 (ou /44 si F N/A, /44 si E N/A, /40 si E+F N/A)
