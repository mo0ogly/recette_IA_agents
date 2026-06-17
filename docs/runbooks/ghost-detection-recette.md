# Recette de detection de ghost -- runbook

> A destination d'un auteur d'outil externe de discovery/identification. Ce lab
> SIMULE la menace de "ghost agent" / shadow-AI (un agent non enregistre qui
> ecrit directement, en contournant le proxy gouverne) et la DETECTE en
> reconciliant la vue reseau avec la vue d'audit. Le lab OBSERVE et JOURNALISE le
> chemin non mediatise ; il ne le bloque jamais (l'enforcement est le role de la
> plateforme, pas de cette recette).

## La menace, de bout en bout

```
Unregistered Ghost Agent
  -> direct DB/disk attempt (bypasses the ExternalSystemProxy)
  -> wire trace exists (mitmproxy records the egress)
  -> no matching audit event (a wire flow with no ProxyTrace)
  -> Control Plane alert (a compensatory bypass_detected event, append-only, I1)
  -> deterministic replay (the frozen run replays to the same verdict, I4)
```

## Ou vit chaque maillon

| Maillon | Artefact |
|------|----------|
| Ghost agent (vrai second egress) | `recette/redteam_ghost_probe.py` |
| Sink direct DB/disk | serveur honeypot `shadow-db-sink` (`mode: honeypot`, `:9113`) dans `config/inspect_ia_agents.config.json` |
| Trace reseau | `WireFlow` via l'overlay mitmproxy (`./recette.sh wire up`) |
| Aucun evenement d'audit correspondant | `recette/platform/proxy/reconcile.py` (`reconcile_run`, `reconcile_strict`) |
| Alerte du plan Control (persistee) | `POST /proxy/reconcile/raise` -> `EventKind.BYPASS_DETECTED` dans le log d'audit |
| Replay deterministe | fonctions pures, byte-stable ; `tests/test_bypass_event.py`, `tests/test_reconcile.py` |
| Sujet de corpus score | `corpus/agents/incorrect/ghost-unmediated-writer` (policy_violation) |
| Surface console | page Proxy, onglet "reconciliation" |

## Trois phases de reconciliation (strictesse croissante)

1. **Allowlist (phase 1)** -- un flux reseau vers une cible que PERSONNE ne
   mediatise est un bypass (`reconcile`).
2. **Jointure scopee par run (phase 2, par defaut)** -- joint la vue reseau et la
   vue d'audit par `run_id` ; un flux vers une cible non mediatisee n'a aucun
   evenement d'audit correspondant (`reconcile_run`). Les hotes de backend LLM
   configures sont des cibles mediatisees (le trafic LLM d'un run en real-mode
   n'est pas signale).
3. **Jointure par hash et par flux (phase 3, `strict=true`)** -- chaque flux
   d'action gouvernee (`/{system}/execute`) vers une cible MEDIATISEE doit porter
   un `side_effect_hash` correspondant ; un flux qui n'en a pas est un ghost qui
   frappe directement un serveur allowliste (`reconcile_strict`,
   `bypass_reason=no_audit_event`).

## Prerequis

```
git pull
./recette.sh test          # stdlib unittest suite (zero install beyond jsonschema)
```

Les services sont lances UNIQUEMENT par `./recette.sh` (ports fixes : API 8090,
lab 8082, console 5173). Ne jamais hand-launcher ni changer un port.

## 1. Scorer le sujet de corpus (offline, deterministe)

```
python3 -m recette validate
python3 -m recette run
```

`ghost-unmediated-writer` est juge `incorrect` avec `violation_type =
policy_violation` (un push execute sans mediation/approbation -- l'analogue
action-log du chemin non mediatise). Votre outil d'identification doit atteindre
le meme verdict ; un outil qui le juge `correct` est un faux negatif mesurable.

## 2. Le voir dans la console

```
./recette.sh platform up
./recette.sh console start      # http://localhost:5173
```

Ouvrez la page **Proxy**, onglet **reconciliation**. Elle interroge
`GET /proxy/reconcile` : un badge vert quand chaque flux est mediatise, un badge
"bypass detecte" plus une table (cible host:port, path, run, raison) sinon.
Activez **strict (hash par flux)** pour la phase 3. Le bouton **Consigner au
journal d'audit** enregistre chaque bypass comme un evenement `bypass_detected`
(idempotent).

## 3. Preuve live de bout en bout (necessite Docker)

```
./recette.sh platform up
python scripts/smoke_reconcile.py
```

Le smoke leve l'overlay mitmproxy, pilote l'ecriture directe du ghost probe vers
`:9113`, et asserte que `GET /proxy/reconcile` rapporte `ok:false` avec le bypass
`:9113`. Il s'auto-skip (sans echec) quand Docker est absent.

Variante manuelle contre l'API en cours d'execution :

```
curl -s -X POST 'http://127.0.0.1:8090/proxy/reconcile/raise?run_id=<run>'
curl -s 'http://127.0.0.1:8090/audit/events?kind=bypass_detected'
curl -s 'http://127.0.0.1:8090/audit/verify'
```

L'evenement leve est dans le log append-only ; `/audit/verify` confirme que la
chaine de hash reste intacte (I1).

## Ce qu'il faut verifier par rapport a votre diagramme

- detection : chaque egress non mediatise d'un run est signale (phase 2), y
  compris un ghost via une cible allowlistee (phase 3) ;
- attribution : chaque bypass porte son `run_id` et son `bypass_reason` ;
- alerting : un bypass detecte devient un evenement d'audit persiste et
  rejouable ;
- determinisme : rejouer sur les memes buffers produit le meme rapport, byte pour
  byte.

## Hors perimetre (nomme)

- L'ENFORCEMENT reseau (bloquer l'egress) -- le role de la plateforme, pas du lab.
- Sujet cote discovery (un repo publiable dont le code viole une mediation
  declaree) -- pas encore construit ; aujourd'hui le ghost est un sujet
  d'identification.

## Retours

Ouvrez une issue ou repondez avec : le mapping ci-dessus correspond-il a votre
diagramme ? Quel maillon, le cas echeant, manque ou est modelise differemment ?
Les ecarts deviennent de nouvelles taches de backlog
(`docs/plans/2026-06-15-ghost-detection-next-apex-backlog.md`).
