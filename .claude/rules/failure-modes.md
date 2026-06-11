# Failure Modes -- comportement fail-safe par defaut

Regle d'or : en cas de defaillance d'un composant de securite, le systeme se ferme
(deny / freeze / buffer), il ne s'ouvre JAMAIS (fail-open interdit, BLOC 7).

## Modes definis

| Composant defaillant | Comportement OBLIGATOIRE | Invariant |
|----------------------|--------------------------|-----------|
| Policy Engine | **default DENY** -- aucune action ne passe | I2 |
| Event Bus (NATS) degrade | **buffer local + retry**, AUCUNE execution externe entre-temps | I1, I5 |
| Approval system | **escalate ou freeze** l'execution -- jamais auto-approve | I6 |
| Audit store incoherent | declenche le **pipeline de validation par replay** | I1, I4 |
| Identity Service down | DENY (action non liable a une identite = refusee) | I3 |
| External proxy down | echec de l'action + evenement d'echec auditable, pas de bypass | I5 |

## Regles d'implementation

1. Chaque nouveau composant DOIT documenter son failure mode dans son module (doc-comment)
   ET le rendre fail-safe.
2. Un timeout est un mode de defaillance : il declenche un comportement explicite
   (deny/escalate/freeze), jamais une voie de contournement.
3. Le buffer local en cas de bus degrade est borne et persistant ; il ne perd pas
   d'evenements et ne reordonne pas (I1).
4. Tout passage en mode degrade est lui-meme un evenement audite.

## Anti-patterns

```rust
// INTERDIT -- fail-open : si la policy plante, on laisse passer
let decision = policy.evaluate(&event).unwrap_or(Decision::Allow);

// CORRECT -- fail-safe : toute incertitude => deny
let decision = match policy.evaluate(&event) {
    Ok(d) => d,
    Err(e) => {
        tracing::error!(error = %e, event_id = %event.event_id, "policy eval failed -> deny");
        Decision::Deny
    }
};
```

## Test de resilience

Les modes de defaillance sont testables (et DOIVENT l'etre) via injection de fautes :
kill du process bus, latence reseau, store en lecture seule. Voir le skill `chaos-engineer`
pour les patterns d'experimentation (local-first).
