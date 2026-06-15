# Design -- adversarial detection loop (wire-vs-audit, first slice)

Date : 2026-06-15
Status : DESIGN APPROVED
Invariants : I1 (audit immuable), I2 (mediation), I4 (replay), I5 (proxy side-effects)
Parent : docs/plans/2026-06-15-adversarial-verification-apex.md (full plane)

## Objectif

Premier increment de la tranche verticale du plan adversarial : prouver, bout en
bout, la **detection d'un chemin non medie** (ghost agent). Le lab SIMULE et
OBSERVE ; il n'enforce pas le blocage reseau.

## Decisions de design (brainstorm 2026-06-15)

1. **Bypass = vrai 2e chemin.** La probe detient un client HTTP direct
   (`recette/_http_client.py` StdlibHttpClient, PAS l'`ExternalSystemProxy`) et
   ecrit vers le honeypot. La divergence wire-sans-audit est reelle, pas fabriquee.
2. **Reconciliation = target-allowlist.** Un run legitime ne parle qu'aux cibles
   mediees connues (lab `:8082`, mock_local `:9101-:9112`, base_urls LLM resolues).
   Tout flux wire vers une cible HORS allowlist = bypass. Pas de join canonique
   (formes wire et audit differentes ; le couplage par cible suffit et est robuste).
3. **Scope = tranche verticale.** Honeypot + probe-bypass + validator + smoke. Les
   autres composants (ghost-identity etendus, overreach scorecard, chaos) = phase 2.

## Architecture & data flow

```
probe-bypass run
  |-- chemin gouverne ---> ExternalSystemProxy --> lab (:8082 / :9101-:9112)
  |                            -> ProxyTrace + event d'audit (I1/I5)
  |
  |-- chemin DIRECT (StdlibHttpClient) ---> honeypot direct-sink (:9113)
                               -> AUCUN ProxyTrace, AUCUN event d'audit

les deux chemins -> overlay mitmproxy -> WireFlowRecorder (POST /proxy/wire)

AuditConsistencyValidator.reconcile(wire_flows, audit_events, allowlist):
  bypass = [f for f in wire_flows if target(f) not in allowlist]
  -> ReconcileReport{ ok: bypass == [], bypass_flows: [...] }
```

- **Honeypot `direct-sink` `:9113`** : faux DB/disk, repond 200, logge chaque hit.
  HORS catalog gouverne et HORS `HANDLER_MODULES` (c'est un sink, pas une action).
  Serveur a part entiere dans la registry, mode special non-governe, lifecycle
  `./recette.sh` (R19, jamais hand-launch). Il ne doit JAMAIS apparaitre dans un
  run legitime -> sa seule presence sur le wire est deja un signal.
- **Probe `probe-bypass`** : corpus/sim subject + runtime agent ; en plus de son
  chemin proxy, un client direct vers `:9113`.
- **Validator** : `recette/platform/proxy/reconcile.py`, fonction PURE.

## Determinisme (I4)

Le vrai 2e chemin = HTTP reel, non deterministe en timing. Resolution = pattern repo :
- `reconcile()` est **pure** (set-diff allowlist sur des inputs donnes) -> testee en
  unittest sur flux + events **seedes**, zero reseau, byte-stable.
- Le chemin live (probe reelle -> :9113 -> mitmproxy -> recorder) est prouve dans le
  **smoke** (`scripts/smoke_reconcile.py`), pas en unittest.

## Composants / fichiers

| Fichier | Role |
|---|---|
| serveur `direct-sink` (config `:9113` + `./recette.sh`) | honeypot, logge les hits |
| corpus/sim `probe-bypass` + runtime agent | la probe au 2e chemin |
| `recette/platform/proxy/reconcile.py` | `reconcile(wire, audit, allowlist) -> ReconcileReport` (pur) |
| `recette/api/routers/proxy.py` : `GET /proxy/reconcile?run_id=` | expose le rapport |
| `tests/test_reconcile.py` | reconcile pur + replay (seede) |
| `scripts/smoke_reconcile.py` | preuve live wire-vs-audit |

## Error handling / edges

- Allowlist = registry serveurs + base_urls LLM resolues. Cible **non classifiable
  = SUSPECT (flag)**, jamais allow silencieux (deny-by-default de classification).
- Verifier que `direct-sink` n'entre PAS dans coverage-guard D4 (pas un domaine catalog).
- `reconcile` borne (le WireFlowRecorder est deja un ring borne) ; pas d'horloge (seq).

## Testing

- Unittest : `reconcile` pur (bypass detecte / run propre = ok), determinisme (2 appels
  identiques), edge cible-suspecte.
- Smoke : overlay up, run la probe, assert le rapport leve le flux `:9113`.
- Gates : `make gates`, `make recette` (coverage-guard reste vert), `./recette.sh smoke`.

## Hors scope (phase 2)

Ghost-identity negatifs etendus, capability-overreach scorecard, fault-injection
(chaos), Meta-Governance des probes, onglet console. Et l'enforcement reseau reel
(isolation pod + handshake I3) qui reste le job de la plateforme cible.
