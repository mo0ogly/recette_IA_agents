---
description: Verification pre-commit (build + anti-patterns + diff)
---

Verification pre-commit complete :

1. **Build Go** : `go build ./cmd/sigma_web/`
2. **Build React** : `cd sigma-react-frontend && npm run build 2>&1 | tail -20`
3. **Anti-patterns scan** sur les fichiers modifies (`git diff --name-only`) :
   - `grep -n "fmt.Println\|console.log\|localhost:8081\|Grid item" [fichiers]`
   - `grep -n "TODO\|FIXME\|HACK\|placeholder\|mock\|dummy" [fichiers]`
4. **Diff review** : `git diff --stat` pour le resume

**Verdict :**
- PASS : "Pre-commit OK. Suggestion de message : `[type]([scope]): [description]`"
- FAIL : lister chaque probleme avec fichier:ligne
