---
name: test-first
description: Impose l'ecriture et l'execution de tests unitaires pour chaque fonction Go ou composant React cree ou modifie. Se declenche AUTOMATIQUEMENT apres toute creation/modification de fonction Go, handler API, composant React, hook, ou service. Produit le fichier de test dans le bon emplacement et l'execute. INTERDIT de declarer "termine" sans test vert.
---

# Test First - Recette unitaire obligatoire

Chaque fonction creee ou modifiee DOIT avoir un test unitaire
qui s'execute et passe AVANT de declarer le travail termine.

## REGLE ABSOLUE

**PAS DE CODE SANS TEST. PAS DE "TERMINE" SANS TEST VERT.**

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_TEST_{FUNCTION}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Declenchement automatique

Cette skill s'active APRES :
- Creation d'une nouvelle fonction Go
- Creation d'un nouveau handler API
- Modification d'une fonction existante (logique metier changee)
- Creation d'un composant React avec logique
- Creation d'un hook custom
- Creation d'un service TS

Elle ne s'active PAS pour :
- Modifications cosmetiques (renommage, formatage)
- Ajout de commentaires/documentation
- Modifications de configuration

---

## Go : tests unitaires

### Ou placer le test

| Code modifie | Test a creer/modifier |
|-------------|----------------------|
| `pkg/validator/recipe/phase04.go` | `pkg/validator/recipe/phase04_test.go` |
| `pkg/compliance/scorer.go` | `pkg/compliance/scorer_test.go` |
| `pkg/model/functions.go` | `pkg/model/functions_test.go` |
| `cmd/sigma_web/compliance_api.go` | `recette/api/XX_test_compliance.sh` (API = test bash) |
| `pkg/discovery/scanner.go` | `pkg/discovery/scanner_test.go` |

**Regle : `_test.go` dans le meme package que le code teste.**
**Exception : handlers API -> test bash dans `recette/api/`.**

### Pattern test Go

```go
package recipe

import "testing"

func TestNomDeLaFonction_CasNormal(t *testing.T) {
    // Arrange
    input := prepareTestInput()

    // Act
    result, err := FonctionTestee(input)

    // Assert
    if err != nil {
        t.Fatalf("erreur inattendue: %v", err)
    }
    if result.Count != 5 {
        t.Errorf("attendu 5, obtenu %d", result.Count)
    }
}

func TestNomDeLaFonction_CasErreur(t *testing.T) {
    // Arrange
    input := prepareInvalidInput()

    // Act
    _, err := FonctionTestee(input)

    // Assert
    if err == nil {
        t.Fatal("erreur attendue mais nil")
    }
}
```

### Cas minimum par fonction
- 1 test cas nominal (happy path)
- 1 test cas erreur (input invalide, nil, vide)
- 1 test cas limite si applicable (tableau vide, valeur 0, string vide)

### Executer et verifier
```bash
# Test specifique
go test -v -run TestNomDeLaFonction ./pkg/validator/recipe/

# Tout le package
go test -v ./pkg/validator/recipe/...

# Avec couverture
go test -cover ./pkg/validator/recipe/...
```

**GATE : le test doit passer (exit code 0) avant de continuer.**

---

## Go : tests API (handlers)

### Ou placer le test
`recette/api/XX_test_nom_endpoint.sh`

Suivre la numerotation existante (00, 01, 02...).

### Pattern test API bash

```bash
#!/bin/bash
# =============================================================================
# Test XX: Nom du test
# Description de ce qui est teste
# =============================================================================

set -e
source "$(dirname "$0")/.env" 2>/dev/null || true

API_BASE_URL="${API_BASE_URL:-http://localhost:8081}"
RESULTS_DIR="$(dirname "$0")/results"
mkdir -p "$RESULTS_DIR"
RESULT_FILE="$RESULTS_DIR/XX_nom_$(date +%Y%m%d_%H%M%S).json"

echo "============================================="
echo "TEST XX: NOM DU TEST"
echo "============================================="

PASSED=0
FAILED=0

# Test 1: Description
echo -n "  Test 1: Description... "
RESPONSE=$(curl -s -w "\n%{http_code}" "$API_BASE_URL/api/endpoint")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "PASS"
    PASSED=$((PASSED + 1))
else
    echo "FAIL (HTTP $HTTP_CODE)"
    FAILED=$((FAILED + 1))
fi

# Resume
echo ""
echo "============================================="
echo "RESULTATS: $PASSED passed, $FAILED failed"
echo "============================================="

if [ $FAILED -gt 0 ]; then
    exit 1
fi
```

### Executer
```bash
# Backend doit tourner
./cleanup_services.sh backend
bash recette/api/XX_test_nom_endpoint.sh
```

---

## React/TypeScript : tests

### Ou placer le test

| Code modifie | Test a creer |
|-------------|-------------|
| `src/components/Dashboard.tsx` | `src/components/Dashboard.test.tsx` |
| `src/hooks/useCompliance.ts` | `src/hooks/useCompliance.test.ts` |
| `src/services/ValidationService.ts` | `src/services/ValidationService.test.ts` |

### Pattern test React (si Jest/Vitest dispo)

```typescript
import { render, screen } from '@testing-library/react';
import { Dashboard } from './Dashboard';

describe('Dashboard', () => {
  it('affiche le titre', () => {
    render(<Dashboard />);
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('gere le cas sans donnees', () => {
    render(<Dashboard data={[]} />);
    expect(screen.getByText('Aucune donnee')).toBeInTheDocument();
  });
});
```

### Si pas de framework de test React configure
Creer un test de type-check minimal :
```bash
# Verifier que le composant compile
cd sigma-react-frontend && npx tsc --noEmit
```

Et un test fonctionnel bash si le composant a une API :
```bash
# Test de l'endpoint que le composant appelle
curl -s http://localhost:8081/api/endpoint | jq '.status'
```

---

## Moteur LIA-Scan : tests de regles

### Pattern test moteur
```bash
# Dans le repertoire de la regle
cd lia_rules/rule_analysis/TECH/VULN/A-VULN-NomRegle/

# Executer le moteur sur test_data.json
bin/lia_scan_engine -multi -rules . -events test_data.json \
  -quadrigramme TEST -date $(date +%Y%m%d) 2>&1

# Verifier : resultats attendus vs obtenus
```

---

## Workflow complet

Quand une fonction est creee/modifiee :

```
1. CODER la fonction
2. CREER le fichier test (meme package, bon emplacement)
3. ECRIRE les cas de test (nominal + erreur + limite)
4. EXECUTER les tests
5. Si FAIL -> corriger le code, pas le test
6. Si PASS -> montrer le resultat a l'utilisateur
7. GATE : "Tests verts. Voici le resultat : [output]"
```

## Anti-patterns

| INTERDIT | CORRECT |
|----------|---------|
| "J'ai cree la fonction, c'est termine" | "J'ai cree la fonction + le test, voici le resultat" |
| Test qui teste rien (`assert true`) | Test qui verifie le comportement reel |
| Test avec donnees mockees/fictives | Test avec donnees realistes (R4) |
| Modifier le test pour qu'il passe | Modifier le code pour que le test passe |
| Test dans un fichier temporaire | Test dans le bon emplacement (`_test.go`, `recette/api/`) |
| "Le test marchera quand le backend tournera" | Executer le test MAINTENANT et montrer le resultat |

## Integration avec d'autres skills

| Apres... | test-first fait... |
|----------|-------------------|
| `/apex` etape 03 (execute) | Cree + execute les tests pour chaque fichier modifie |
| `/debug-go` phase 3 (corriger) | Ajoute un test de regression pour le bug corrige |
| `/analyze-repo` phase 5 (implementation) | Cree les tests pour chaque fonctionnalite transposee |
| Toute creation de handler API | Cree `recette/api/XX_test_*.sh` |
