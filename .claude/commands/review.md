---
description: Review les changements en cours (staged + unstaged)
---

Effectue une code review des changements en cours :

1. Execute `git diff` pour voir les modifications unstaged
2. Execute `git diff --cached` pour voir les modifications staged
3. Review chaque fichier modifie selon les criteres LIA-SEC :

**Checklist review :**
- [ ] Pas de `fmt.Println()` / `console.log()` (R6 - logger custom obligatoire)
- [ ] Pas de `http://localhost:8081` hardcode (ConfigurationService)
- [ ] Pas de `fetch()` brut (fetchWithConfig obligatoire)
- [ ] Pas de `<Grid item xs=` (MUI v7 : `<Grid size={{ xs: }}>`)
- [ ] Pas de TODO, placeholder, mock, donnees fictives (R4)
- [ ] Pas d'emoji (R10)
- [ ] Error handling present (pas de `_` sur les erreurs Go)
- [ ] Pas de secrets exposes (.env, credentials, API keys)
- [ ] SQL parametre (pas de concatenation de strings)
- [ ] Nommage explicite (variables, fonctions, fichiers)

**Format de sortie :**
```
FICHIER : [path]
  CRITICAL : [issues bloquantes]
  WARNING  : [a corriger avant commit]
  OK       : [ce qui est bien]
```

Si tout est propre : "Review OK - pret a commit."
