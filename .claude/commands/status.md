---
description: Etat rapide du projet (git, services, build)
---

Donne un etat rapide du projet LIA-SEC :

1. **Git** : branche courante, fichiers modifies non commites, dernier commit
2. **Services** : execute `./cleanup_services.sh status` pour verifier backend (8081) et frontend (3000)
3. **Build Go** : execute `go build ./cmd/sigma_web/ 2>&1 | tail -5` pour verifier la compilation
4. **Build React** : execute `cd sigma-react-frontend && npx tsc --noEmit 2>&1 | tail -10` pour verifier les types

Presenter les resultats en format compact :
```
GIT     : [branche] | [N fichiers modifies] | dernier commit: [message]
BACKEND : [running/stopped] port 8081
FRONTEND: [running/stopped] port 3000
GO BUILD: [OK/ERREUR]
TS CHECK: [OK/N erreurs]
```
