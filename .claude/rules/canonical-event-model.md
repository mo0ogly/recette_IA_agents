# Canonical Event Model -- AgentActionEvent

Toute action d'agent est normalisee en `AgentActionEvent` par la Gateway AVANT toute
decision. C'est le contrat central du systeme. JAMAIS inventer ou supprimer un champ
sans migration de schema versionnee.

## Schema canonique

| Champ | Type | Role | Invariant |
|-------|------|------|-----------|
| `event_id` | ULID / UUIDv7 | identifiant unique, ordonnable temporellement | I1 |
| `timestamp` | ts capture | horloge capturee de maniere deterministe (input, pas `now()` en decision) | I4 |
| `agent_id` | identite | agent liee cryptographiquement | I3 |
| `capability_scope` | set/struct | capacites assignees a l'agent | I2 |
| `action_type` | enum/string | type d'action demandee | - |
| `target_system` | string | systeme externe cible | I5 |
| `payload` | bytes/json | donnees de l'action | - |
| `risk_score` | number | sortie du Risk Engine (sensibilite, blast radius, confiance) | - |
| `policy_decision` | enum | `allow` \| `deny` \| `escalate` (+ version de policy) | I2, I4 |
| `approval_state` | enum | `none` \| `pending` \| `approved` \| `denied` \| `timeout` | I6 |
| `side_effect_hash` | hash | hash de l'effet de bord produit par le proxy | I1, I5 |

## Regles de modelisation

1. `event_id` est ordonnable (ULID/UUIDv7) pour garantir un ordre stable au replay.
2. `timestamp` est un INPUT capture, jamais lu via `now()` dans le chemin de decision (I4).
3. `policy_decision` enregistre la **version de policy** appliquee (replay deterministe).
4. Le `payload` est traite comme opaque par la Gateway ; sa validation appartient au Policy Engine.
5. Versioning : tout evenement porte une version de schema. Une evolution de schema = nouvelle
   version + adaptateur de lecture. JAMAIS de migration destructive du log (I1).

## Representation Rust recommandee

- `AgentActionEvent` = struct serialisable (serde) avec enums fortement types pour
  `policy_decision` et `approval_state` (pas de string magique).
- Les transitions d'etat (`approval_state`) sont modelisees par une state machine
  (discriminated enum), pas par des flags booleens disjoints.
- Sérialisation versionnee : prevoir un champ `schema_version` ou un envelope.

## Anti-patterns

- Ajouter un champ ad-hoc dans le payload pour "porter" une decision -> doit etre un champ de premiere classe versionne.
- Reutiliser `event_id` pour deux evenements logiques distincts.
- Stocker `policy_decision` sans la version de policy -> casse I4.
