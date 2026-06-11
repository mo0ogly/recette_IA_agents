# Architecture multi-plan -- Control / Data / Audit

AgentRail est structure en trois plans aux responsabilites disjointes. La frontiere
entre plans est une frontiere de securite : un plan ne court-circuite jamais un autre.

## Control Plane -- "ce qui est autorise"

Composants : API Gateway (Axum), Policy Engine, Identity Service, Risk Engine, Approval Orchestrator.

Responsabilites :
- Normaliser l'action entrante en `AgentActionEvent`.
- Resoudre et verifier l'identite de l'agent (I3).
- Evaluer la policy : `allow` / `deny` / `escalate` (I2).
- Calculer le `risk_score` (sensibilite, blast radius, confiance).
- Declencher l'approbation humaine via Temporal quand requise (I6).
- Assigner / contraindre les capacites (`capability_scope`).

Regles :
- DENY par defaut (deny-by-default) : une action non couverte par une policy est refusee.
- Le chemin de decision est deterministe (I4) : voir `determinism-replay.md`.
- Aucun effet de bord externe ici : le Control Plane decide, il n'execute pas.

## Data Plane -- "executer et transporter"

Composants : Event Bus (NATS JetStream), Execution Workers, External System Proxies, Realtime Transport.

Responsabilites :
- Executer UNIQUEMENT des actions validees (`policy_decision = allow`, ou `approved`).
- Emettre des evenements immuables (I1).
- Communiquer avec les systemes externes EXCLUSIVEMENT via les proxies (I5).
- Diffuser les mises a jour d'etat en temps reel.

Regles :
- Un worker ne re-decide pas : il execute une decision deja prise par le Control Plane.
- Tout appel externe produit un `side_effect_hash` enregistre dans l'evenement.
- Degradation du bus -> buffer local + retry, AUCUNE execution externe entre-temps (voir `failure-modes.md`).

## Audit Plane -- "verite, historique, replay"

Composants : Event Store, Replay Engine, Observability stack, Logging subsystem.

Responsabilites :
- Stocker le log d'evenements immuable (I1).
- Reconstruire l'historique complet d'execution.
- Permettre le replay deterministe (I4).
- Fournir une piste d'audit de qualite forensique.

Regles :
- Append-only. Pas d'UPDATE/DELETE.
- Les projections/read-models sont reconstructibles depuis le log (jetables).
- L'incoherence du store declenche le pipeline de validation par replay.

## Frontieres (a ne jamais violer)

```
Agent -> [Control Plane: Gateway -> Policy -> Risk -> Approval] -> decision
                                                                      |
                                              allow/approved          v
                                   [Data Plane: Workers -> Proxies] -> external system
                                                  |
                                                  v emit event
                                   [Audit Plane: Event Store (append-only)]
```

- Agent -> external system SANS passer par le Control Plane : INTERDIT (I2).
- Logique metier -> external system SANS proxy : INTERDIT (I5).
- Mutation d'un evenement committe : INTERDIT (I1).
