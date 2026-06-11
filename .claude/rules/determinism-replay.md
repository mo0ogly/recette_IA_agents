# Determinism & Replay (I4) -- le chemin de decision doit etre rejouable

> Meme event stream + meme version de policy => replay produit un resultat identique.

C'est la propriete qui rend l'audit forensique et la reconstruction d'historique possibles.
Toute source de non-determinisme dans le chemin de decision casse I4.

## Sources de non-determinisme INTERDITES dans le chemin de decision

| Source | Interdit | Alternative |
|--------|----------|-------------|
| Horloge | `SystemTime::now()`, `Instant::now()`, `chrono::Utc::now()` | capturer dans `event.timestamp` (input) |
| Aleatoire | `rand::*`, UUIDv4 genere pendant la decision | UUIDv7/ULID genere en amont et capture |
| I/O reseau | lecture HTTP/DB pendant l'evaluation | injecter la donnee comme input capture |
| Iteration non ordonnee | `HashMap` iteration order | `BTreeMap` / ordre explicite |
| Concurrence | resultat dependant de l'ordre d'ordonnancement | decision pure, deterministe |
| Float non reproductible | comparaisons flottantes instables | seuils entiers / arithmetique stable |

## Principe : decision = fonction pure

```
decide(event: &AgentActionEvent, policy: &PolicyVersion) -> Decision
```

`decide` ne lit que ses arguments. Toutes les donnees variables (horloge, contexte externe,
seuils) sont soit dans `event`, soit dans `policy` (versionnee). Les effets de bord
(I/O, appels externes) sont hors de `decide` -- ils appartiennent au Data Plane via proxy (I5).

## Capture du non-determinisme

Quand une donnee non-deterministe est NECESSAIRE a la decision (ex: heure de la requete pour
une regle horaire), elle est **capturee en amont** par la Gateway et **enregistree dans
l'evenement** comme input. Le replay relit cet input, ne le regenere pas.

## Versioning de policy

- La version de policy appliquee est enregistree avec la decision (`policy_decision`).
- Le Replay Engine charge la version exacte de policy pour rejouer -- jamais "la derniere".
- Un changement de policy ne reecrit pas l'histoire : les anciens evenements gardent leur
  decision sous leur version (I1).

## Test de replay (OBLIGATOIRE pour tout chemin de decision)

```rust
#[test]
fn replay_is_deterministic() {
    let stream = load_fixture_stream("known_stream.jsonl");
    let policy = load_policy_version("v3");
    let run_a = replay(&stream, &policy);
    let run_b = replay(&stream, &policy);
    assert_eq!(run_a, run_b);                 // determinisme
    assert_eq!(run_a, load_golden("known_stream.golden"));  // resultat attendu
}
```

Un PR qui ajoute/modifie de la logique de decision sans test de replay est INCOMPLET (R3, R11).
