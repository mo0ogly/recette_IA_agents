# Event Store -- decision de persistance (NON FIGEE)

> Statut : OUVERT. Le choix de la persistance de l'event store n'est pas tranche.
> Ce fichier documente les options et les criteres. NE PAS coder de couplage fort a une
> implementation tant que la decision n'est pas prise et inscrite ici (passer en "FIGE").

## Contraintes imposees par les invariants

Quel que soit le choix, le store DOIT garantir :
- **I1** : append-only, immuable apres commit (pas d'UPDATE/DELETE du log).
- **I4** : ordre stable et reproductible des evenements (replay deterministe).
- Reconstruction des projections/read-models depuis le log seul.
- Integrite verifiable (hash chain / `side_effect_hash`).

## Options evaluees

### Option A -- PostgreSQL event-sourcing
- Log = table append-only `events` (PK `event_id` ULID, ordre par sequence monotone).
- Projections = tables read-model reconstruites par des handlers.
- NATS JetStream pour le transport temps reel (pas la source de verite).
- Pour : ecosysteme Rust mur (`sqlx`), transactions, requetes riches, ops simples.
- Contre : ordre global a gerer (sequence), throughput d'append a surveiller.

### Option B -- EventStoreDB (Kurrent)
- Store dedie event-sourcing : streams, immutabilite, subscriptions natives.
- PostgreSQL pour les read-models/projections.
- Pour : semantique event-sourcing native, ordering par stream, replay first-class.
- Contre : composant supplementaire a operer, ecosysteme Rust moins mur.

### Option C -- NATS JetStream comme source de verite
- Stream persistant JetStream = event log ; projections materialisees ailleurs.
- Pour : un seul systeme pour transport + persistance.
- Contre : garanties d'immutabilite/retention a configurer finement, requetage historique limite, risque de purge.

## Criteres de decision

1. Garanties d'immutabilite et de retention illimitee du log.
2. Ordering deterministe (global ou par stream) exploitable au replay.
3. Maturite de l'ecosysteme Rust (driver, tests, ops).
4. Cout operationnel (nombre de composants a maintenir).
5. Capacite de requetage forensique sur l'historique.

## Recommandation par defaut (a confirmer)

En l'absence de contrainte d'echelle extreme connue : **Option A (PostgreSQL event-sourcing)
+ JetStream transport** -- meilleur ratio maturite Rust / simplicite ops / requetage forensique.
A re-evaluer si le throughput d'append ou le besoin de subscriptions natives le justifie.

## Quand cette decision est prise

Remplacer le statut OUVERT par FIGE, dater, et inscrire l'option retenue + justification ici.
Toute la couche persistance doit etre derriere un trait (`EventStore`) pour ne pas coupler
le reste du systeme a l'implementation choisie.
