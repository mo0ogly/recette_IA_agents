---
name: test-first
description: Impose l'ecriture et l'execution de tests unitaires pour chaque fonction Rust, module Python (recette), ou composant React cree ou modifie. Se declenche AUTOMATIQUEMENT apres toute creation/modification de fonction Rust, handler Axum, module recette Python, composant React, hook, ou service. Produit le fichier de test dans le bon emplacement et l'execute. INTERDIT de declarer "termine" sans test vert.
---

# Test First - Recette unitaire obligatoire

Chaque fonction creee ou modifiee DOIT avoir un test unitaire
qui s'execute et passe AVANT de declarer le travail termine.

Le determinisme est loi (I4) : aucun `time.time()` / `datetime.now()` / `random`
(Python) ni `SystemTime::now()` / `rand` (Rust) dans une execution, un chemin de
decision, ou un juge -- l'horloge est injectee, et tout chemin de decision porte
un test de replay byte-stable.

## REGLE ABSOLUE

**PAS DE CODE SANS TEST. PAS DE "TERMINE" SANS TEST VERT.**

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `docs/tracking/PLAN_TEST_{FUNCTION}_{YYYY-MM-DD}.md` (template: `docs/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `docs/tracking/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Declenchement automatique

Cette skill s'active APRES :
- Creation d'une nouvelle fonction Rust
- Creation d'un nouveau handler Axum / module recette Python
- Modification d'une fonction existante (logique metier changee)
- Creation d'un composant React avec logique
- Creation d'un hook custom
- Creation d'un service TS

Elle ne s'active PAS pour :
- Modifications cosmetiques (renommage, formatage)
- Ajout de commentaires/documentation
- Modifications de configuration

---

## Rust : tests unitaires

### Ou placer le test

| Code modifie | Test a creer/modifier |
|-------------|----------------------|
| `src/control/policy.rs` | `#[cfg(test)] mod tests` dans `src/control/policy.rs` |
| `src/audit/event_store.rs` | tests inline OU `tests/event_store.rs` (integration) |
| `src/gateway/handlers.rs` | `#[tokio::test]` inline + test d'integration `tests/` |
| `cmd/gateway/main.rs` | extraire la logique testable dans un module + test inline |

**Regle : test unitaire = module `#[cfg(test)]` dans le meme fichier que le code teste.**
**Test d'integration (API/cross-module) -> `tests/` a la racine de la crate.**

### Pattern test Rust

```rust
// In the same file as the code under test
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nom_de_la_fonction_cas_normal() {
        // Arrange
        let input = prepare_test_input();

        // Act
        let result = function_under_test(&input).expect("should succeed");

        // Assert
        assert_eq!(result.count, 5);
    }

    #[test]
    fn nom_de_la_fonction_cas_erreur() {
        // Arrange
        let input = prepare_invalid_input();

        // Act
        let result = function_under_test(&input);

        // Assert
        assert!(result.is_err(), "erreur attendue mais Ok");
    }
}
```

Pour un handler/chemin async (Axum, proxy) :

```rust
#[tokio::test]
async fn handler_returns_deny_when_policy_engine_down() {
    let app = test_app_with_failing_policy();
    let resp = app.evaluate(&sample_event()).await;
    // Fail-safe par defaut : policy engine down -> DENY (jamais fail-open)
    assert_eq!(resp.policy_decision, PolicyDecision::Deny);
}
```

> `.unwrap()`/`.expect()` sont autorises DANS les tests (interdits en chemin de
> production, R7). Un chemin de decision/replay ship un test de replay
> deterministe (I4) : `assert_eq!(replay(stream), replay(stream))` + golden.

### Cas minimum par fonction
- 1 test cas nominal (happy path)
- 1 test cas erreur (input invalide, vide, `None`/`Err`)
- 1 test cas limite si applicable (slice vide, valeur 0, string vide)

### Executer et verifier
```bash
# Test specifique
cargo test nom_de_la_fonction

# Tout un module / une crate
cargo test --all

# Chemin de decision : valider aussi en release
cargo test --all --release
```

**GATE : le test doit passer (exit code 0) avant de continuer.**

---

## Python : tests recette (harnais `recette/`)

### Ou placer le test

| Code modifie | Test a creer/modifier |
|-------------|----------------------|
| `recette/harness.py` | `tests/test_harness.py` |
| `recette/maf_judge.py` | `tests/test_maf_judge.py` |
| `recette/api/runs.py` | `tests/test_api_runs.py` (lance via `.venv`) |

**Regle : tests sous `tests/`, fixtures sous `tests/fixtures/`. Runner stdlib
`unittest`, zero install hors `jsonschema` (R20). Pas de fichier de test dans `/tmp`.**

### Pattern test Python (unittest stdlib)

```python
import unittest

from recette.harness import judge_subject


class TestJudgeSubject(unittest.TestCase):
    def test_cas_normal(self):
        subject = load_fixture("correct/pr-bot")
        verdict = judge_subject(subject)
        self.assertEqual(verdict.global_verdict, "correct")

    def test_cas_negatif_mono_axe(self):
        subject = load_fixture("incorrect/capability-overreach")
        verdict = judge_subject(subject)
        self.assertEqual(verdict.violation_type, "capability_overreach")


if __name__ == "__main__":
    unittest.main()
```

Tout chemin de decision/juge ship un test de replay byte-stable (I4) :
horloge logique injectee (`recette.events.LogicalClock`), `StubLlm`/`ReplayLlm`.

### Executer
```bash
# Tout le suite
python3 -m unittest discover -s tests
# Ou via le lanceur unique
./recette.sh test
```

---

## React/TypeScript : tests

### Ou placer le test

| Code modifie | Test a creer |
|-------------|-------------|
| `src/components/Dashboard.tsx` | `src/components/Dashboard.test.tsx` |
| `src/hooks/useCompliance.ts` | `src/hooks/useCompliance.test.ts` |
| `src/services/ValidationService.ts` | `src/services/ValidationService.test.ts` |

### Pattern test React (vitest)

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
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

Contract gate (R16) : tout composant appelant une API DOIT etre rendu contre une
fixture payload REELLE dans `__fixtures__/{component}.fixture.json`, asserter au
moins un element DOM, et le service DOIT unwrap l'enveloppe `{ success, data }`.
Pour un composant affichant `approval_state` / `policy_decision`, couvrir chaque
variante de l'union (`none|pending|approved|denied|timeout`, `allow|deny|escalate`).

### Executer
```bash
# Tests console (vitest)
./recette.sh console-test
# Type-check + build
./recette.sh console-build
```

---

## Recette discovery / identification : tests de corpus

Le harnais juge un corpus ground-truth. Apres modif d'un agent du corpus ou du
juge, rejouer la boucle de recette et le coverage guard (R20) :

```bash
# Schema-valide le corpus (agents + repos discovery)
python3 -m recette validate

# Identification -> scorecard 4 dimensions
python3 -m recette run

# Discovery -> scorecard invariants (oracle offline)
python3 -m recette discovery --adapter reference

# Coverage guard : un trou de recette = test rouge (jamais a la main)
python3 -m unittest tests.test_coverage_guard
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
| Test dans un fichier temporaire (`/tmp`) | Test dans le bon emplacement (`#[cfg(test)]`, `tests/`, `__fixtures__/`) |
| "Le test marchera quand le backend tournera" | Executer le test MAINTENANT et montrer le resultat |
| `now()` / `random` dans une execution ou un juge | horloge logique injectee + test de replay deterministe (I4) |

## Integration avec d'autres skills

| Apres... | test-first fait... |
|----------|-------------------|
| `/apex` etape 03 (execute) | Cree + execute les tests pour chaque fichier modifie |
| `/systematic-debugging` (corriger) | Ajoute un test de regression pour le bug corrige |
| `/analyze-repo` phase 5 (implementation) | Cree les tests pour chaque fonctionnalite transposee |
| Toute creation de handler Axum / endpoint API | Cree un test d'integration (`tests/`) + fixture |
| Toute modif du corpus ou du juge recette | Rejoue `python -m recette run` + coverage guard (R20) |
