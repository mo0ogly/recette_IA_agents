# Invariants I1-I6 -- LOI ABSOLUE du systeme inspect_ia_agents

Les invariants sont la specification de securite du systeme. Ils ne sont pas negociables.
Toute PR, toute revue, toute decision d'architecture est evaluee contre eux. Une violation
d'invariant rend la PR INCOMPLETE par definition, peu importe que ca compile ou que les tests passent.

---

## I1 -- Immutabilite des evenements

> Tout evenement committe dans l'event store est immuable.

### Checklist
- [ ] Aucun `UPDATE`/`DELETE`/`TRUNCATE` sur la table/stream d'evenements committes.
- [ ] La correction d'une erreur se fait par un **evenement compensatoire** (nouvel evenement), jamais par mutation.
- [ ] Le schema de la table d'evenements n'a pas de colonne mutable apres commit (pas de `updated_at` sur un evenement).
- [ ] Si JetStream : stream configure `DiscardPolicy` adequat, pas de purge dans le chemin metier.
- [ ] Les projections/read-models sont reconstructibles a partir du log (ils sont jetables, pas l'inverse).

### Anti-pattern
```rust
// INTERDIT -- mutation d'un evenement committe
sqlx::query!("UPDATE events SET payload = $1 WHERE event_id = $2", new, id)
// CORRECT -- evenement compensatoire
append_event(EventKind::Compensation { corrects: id, .. })
```

---

## I2 -- Mediation par le Control Plane

> Aucune action externe ne s'execute sans evaluation du Control Plane.

### Checklist
- [ ] Tout chemin agent -> external system passe par la Gateway puis le Policy Engine.
- [ ] Aucun appel direct depuis un Execution Worker vers un external system sans `policy_decision = allow` prealable lie a l'evenement.
- [ ] Pas de "porte derobee" : recherche `reqwest::`/`hyper::`/client externe dans le Data Plane qui ne passe pas par un proxy mediatise (voir I5).
- [ ] Un nouvel endpoint qui declenche une action est refuse par defaut tant qu'il n'est pas couvert par une policy.

---

## I3 -- Liaison cryptographique a l'identite

> Toute action est liee cryptographiquement a une identite d'agent.

### Checklist
- [ ] Chaque `AgentActionEvent` porte un `agent_id` resolu par l'Identity Service.
- [ ] La requete entrante est signee/authentifiee (token, mTLS, signature) AVANT normalisation.
- [ ] Pas d'action anonyme ni d'`agent_id` fourni en clair non verifie par le client.
- [ ] La verification de signature est dans le chemin de decision et auditee en cas d'echec.

---

## I4 -- Replay deterministe

> Meme event stream + meme version de policy => replay produit un resultat identique.

### Checklist (voir aussi `determinism-replay.md`)
- [ ] Pas de `SystemTime::now()`, `Instant::now()`, `Utc::now()` dans le chemin de decision sans capture dans l'evenement.
- [ ] Pas de `rand`/UUIDv4 genere pendant la decision sans capture.
- [ ] Pas d'I/O reseau/disque qui influence la decision sans etre un input capture.
- [ ] La version de policy appliquee est enregistree dans `policy_decision` (ou un champ dedie).
- [ ] Un test de replay rejoue un stream connu et assert un resultat byte-identique.

---

## I5 -- Side-effects mediats

> Les effets de bord externes ne passent QUE par des interfaces de proxy controlees.

### Checklist
- [ ] La logique metier/decision n'appelle jamais directement un external system.
- [ ] Tout appel externe passe par un `ExternalSystemProxy` (trait) qui produit un `side_effect_hash`.
- [ ] Le proxy est le seul a detenir les credentials de l'external system.
- [ ] Le proxy est mockable en test (trait + impl) pour le replay.

---

## I6 -- Blocage sur approbation

> Une action requerant approbation BLOQUE l'execution jusqu'a resolution ou timeout.

### Checklist
- [ ] `policy_decision = escalate` => l'action passe en `approval_state = pending` et N'EST PAS executee.
- [ ] L'attente d'approbation est portee par Temporal (workflow durable), pas par un sleep en memoire.
- [ ] Un timeout d'approbation declenche un comportement explicite (escalate/freeze/deny), jamais auto-approve.
- [ ] Aucune execution optimiste "en attendant l'approbation".

---

## Application

Quand une tache touche un plane (Control/Data/Audit), enumere dans le plan les invariants
concernes et coche la checklist correspondante avant de declarer la tache terminee.
En cas de doute sur une violation potentielle (< 95% de confiance, BLOC 0) : demander.
