# APEX — Autonomie par instance + tracking multi-session

**Date** : 2026-07-09
**Statut** : Phases 2–8 LIVRÉES (moteur + persistence + console). Reste : i18n fine + éventuelle vue timeline dédiée.

## Livré (2026-07-09)

**Lot moteur (Phases 2–5, 8)**
- `recette/instance.py` — `AgentInstance` (backend propre) + `Conversation.project`
  (projection privée stricte : aucun system/état d'un pair n'est lisible).
- `recette/tracking.py` — `SessionTracker` : fail-loud si `session_id`/`instance_id`
  manquant, reçus content-free chaînés par session (compatibles `context_receipt.verify_chain`),
  index cross-session (`sessions_of`/`instances_of`).
- `recette/orchestrate_ag2.py::drive_ag2` — backends **par instance** (Mapping validé,
  fail-loud sur trou) + tracking systématique par tour.
- Tests : `tests/test_instance.py`, `tests/test_tracking.py`, extension de `tests/test_orchestrate_ag2.py`.

**Lot persistence (Phase 6)**
- `platform/proxy/wire.py` — `WireFlow` + `session_id`/`instance_id` (coercion défensive).
- `platform/proxy/store.py` — colonnes + migration additive gardée + index (`idx_wire_session`/`_instance`),
  filtres `query_wire`/`query`. Migration legacy testée (`tests/test_proxy_store_session.py`).
- `api/routers/proxy.py` — `GET /proxy/wire?session_id=&instance_id=` (suivi cross-session), bout-en-bout vérifié.

**Lot console (Phase 7)**
- `console/src/pages/proxy/wireLayers.ts` — type `WireFlowTracked` + lecteurs `sessionId`/`instanceId`.
- `wireFlowModel.ts` — filtre `sessionId`/`instanceId` (suivre une instance à travers ses sessions).
- `WireLayersView.tsx` — bloc « Instance — tracking multi-session » (affiché même sans décodage réseau).
- `TrackingFilters.tsx` (nouveau) + `WirePanel.tsx` — inputs UI **instance**/**session** dans la barre de
  filtre, deep-linkable via `?instance=`/`?session=`. Extrait en composant (plafond 800 lignes).
- `wireDeltaClient.ts` (nouveau) — `getWireFlowsDeltaTracked` : filtrage **serveur** (session_id/instance_id
  poussés dans la query) SANS éditer `client.ts` (verrouillé par la taille), via le transport `request` exporté.
  Le panel poll désormais par ce wrapper ; reset du feed sur changement de session/instance.
- `wireSessionSummary.ts` + `InstanceSessionSummary.tsx` (nouveaux) — **vue cross-session** : quand une instance
  est épinglée, chips cliquables de chaque session où elle a agi (nb flux + échecs), pour naviguer d'une session
  à l'autre. Le capstone « suivre une instance à travers ses sessions ».
- **i18n** : N/A — le panneau proxy de la console recette est en **français en dur par design** (pas de
  framework i18n dans `pages/proxy`) ; les libellés ajoutés suivent cette convention.

Vérifs finales : backend **2155** (moteur) / **422** (proxy) passed ; front **184 tests** proxy verts ;
`tsc --noEmit` propre ; tous les fichiers ≤ 800 lignes (WirePanel = 798).

Vérifs : backend suite complète **2155 passed** (moteur) ; périmètre proxy/wire/store/instance/tracking
**422 passed, 0 échec** ; front **36 tests** verts + `tsc --noEmit` propre.

**Portée** : `recette/` (orchestration, LLM, proxy/tracking) + console observability

## Problème (mots de l'utilisateur)

> « il faut que les agents puissent être autonomes des serveurs côté LLM. Quand un
> agent discute avec un serveur, chacun ne connaît que ce qu'il connaît de son
> instance — ce n'est PAS une instance d'agent commune aux deux. Ce tracking
> multi-session devrait être le cas à chaque fois. »

Deux exigences :

1. **Isolation par instance** — chaque agent est une instance autonome avec son
   propre backend LLM, son propre contexte (history/mémoire), sa propre identité.
   Quand instance A parle à une instance/serveur B, chacune ne voit que **sa
   projection** de l'échange ; aucun objet d'agent n'est partagé entre les deux.
2. **Tracking multi-session systématique** — chaque échange porte
   `session_id` + `instance_id`, toujours (fail-loud si absent), et le tracking
   relie une même instance **à travers plusieurs sessions**.

## État actuel (constats de code)

| Brique existante | Ce qu'elle fait | Manque vs la demande |
|---|---|---|
| `recette/agent_proc.py` | Isolation **OS** : 1 agent = 1 process, `comm`=agent_id, connects TCP attribués eBPF | Pas d'isolation au niveau **contexte/conversation** |
| `recette/orchestrate.py::drive` (group_chat) | 1 `backend` + 1 `history` **partagés** par tous les speakers | Instance commune → viole l'exigence 1 |
| `recette/orchestrate_ag2.py::drive_ag2` | Idem : **un seul `RecetteAG2Client(backend=…)` partagé** par tous les agents | Instance commune → viole l'exigence 1 |
| `recette/platform/passport_middleware.py`, `admission.py` | **Agent passport** = identité d'agent admise (ancre naturelle d'`instance_id`) | À confirmer comme clé d'instance |
| `recette/context_receipt.py` | Reçus content-free **chaînés par hash** (I1), champs `agent_id`/`target_system`/`run_id` | **Aucun `session_id`** ; pas d'index cross-session |
| `recette/platform/proxy/wire.py` (`WireFlow`) | Trace agent↔serveur, `run_id` optionnel | Pas de `session_id`/`instance_id` ; tracking non obligatoire |

**Contrainte à respecter** (RETEX 2026-04-08) : ne jamais mixer des providers
entre agents **par accident** (fallback caché Ollama/Groq → freeze). Ici, des
backends par instance sont **intentionnels et explicites** — compatible avec la
RETEX tant que chaque instance déclare son provider et que rien ne « fallback »
en silence. Le tracker enregistre le provider/model effectif par instance.

## Invariants à préserver

- **I4 déterminisme** : per-instance `StubLlm`/`ReplayLlm` → run rejouable.
- **I1 audit** : reçus chaînés par hash, séquence par session, cross-session vérifiable.
- **R8 clés write-only** : le backend (et sa clé) vit dans l'instance, jamais dans le JSON de trace.
- **R20/R22** : pas de dépendance lourde nouvelle ; AG2 reste l'extra optionnel.

---

## Plan APEX (10 phases)

### Phase 1 — Cadrage & ancre d'identité
- Confirmer que l'**agent passport** (admission) est la clé d'`instance_id` (lire
  `passport_middleware.py`, `admission.py`, `2026-07-05-agent-passport-design.md`).
- Décision : `instance_id` = identité **stable** d'une instance d'agent **à travers
  les sessions** ; `session_id` = identité d'**une** conversation/épisode.
- Livrable : section « modèle d'identité » validée, pas de code.

### Phase 2 — Modèle de données `AgentInstance` + `Conversation`
- Nouveau `recette/instance.py` :
  - `@dataclass(frozen=True) AgentInstance` : `instance_id`, `role`, `system`,
    `backend: LlmBackend` (le SIEN), `capability_scope`, `provider`, `model`.
  - `Conversation` : échange ordonné entre deux `instance_id`. Chaque instance a
    sa **projection privée** (`history` propre) ; méthode `project(instance_id)`
    ne renvoie QUE les messages adressés à/depuis cette instance — jamais le
    `system`/raisonnement de l'autre.
- Test d'isolation dès cette phase (voir Phase 8).

### Phase 3 — Contrat de tracking systématique
- Nouveau `recette/tracking.py` :
  - `@dataclass TrackedExchange` : `session_id`, `instance_id`, `peer_id`, `seq`,
    + les champs `ProxyTrace` existants (target, action, ok, digests).
  - `SessionTracker.record(exchange)` : **exige** `session_id` ET `instance_id`
    non vides → `ValueError` sinon (fail-loud = « à chaque fois »). Chaîne les
    reçus **par session** (réutilise `context_receipt.chain_receipts`).
  - Index cross-session : `instances_of(session_id)`, `sessions_of(instance_id)`.
- Le tracking devient une **dépendance dure** du chemin d'exécution (pas un opt-in).

### Phase 4 — Isolation par instance dans l'orchestrateur
- `orchestrate_ag2.drive_ag2` : remplacer le `backend` unique par un
  `backends: dict[instance_id, LlmBackend]` → **chaque** `ConversableAgent` reçoit
  son propre `RecetteAG2Client(backend=backends[id])`. Le manager a le sien.
- `orchestrate.drive` (natif) : idem, `backend` → `backends` par participant ;
  chaque instance garde son `history` privé (fin de l'history partagée).
- Rétro-compat : si un seul backend est fourni, le répliquer par instance **avec
  des clients distincts** (isolation d'objet préservée même si même provider).

### Phase 5 — Câblage tracking dans les runs
- `drive`/`drive_ag2` émettent un `TrackedExchange` par tour, via `SessionTracker`.
- `OrchestrationRun` gagne `session_id` ; chaque `ToolCall`/hop porte `instance_id`.
- Un `run` sans `session_id` est rejeté (fail-loud) → tracking garanti.

### Phase 6 — Persistence & schéma
- `platform/proxy/wire.py` : `WireFlow` + `session_id`, `instance_id` (nullable →
  puis requis à l'écriture via le tracker).
- `platform/proxy/store.py` : colonnes `session_id`, `instance_id` + migration
  `ALTER TABLE` gardée par `PRAGMA table_info` (même pattern que la migration
  `layers` déjà faite) ; index `(instance_id)` et `(session_id)`.
- Table d'index cross-session `instance_sessions(instance_id, session_id, first_seq)`.

### Phase 7 — Surface console (observability multi-session)
- WirePanel/observability : grouper par `session_id`, filtrer par `instance_id`,
  vue **« Suivre l'instance à travers les sessions »** (timeline cross-session).
- Réutilise le layered decode déjà livré ; ajoute une colonne session/instance.
- i18n FR/EN/BR pour les nouveaux libellés.

### Phase 8 — Tests
- **Isolation** : `Conversation.project(A)` ne contient jamais le `system`/history
  de B ; deux instances avec `StubLlm` distincts ne partagent aucun état.
- **Déterminisme (I4)** : run per-instance `StubLlm` reproductible ; `replay` OK.
- **Tracking obligatoire** : `SessionTracker.record` sans `session_id`/`instance_id`
  lève `ValueError`.
- **Cross-session** : même `instance_id` sur 2 sessions → reçus chaînés par session,
  `sessions_of(instance_id)` renvoie les deux, `verify_chain` OK par session.
- **Non-régression** : suite `orchestrate` + `orchestrate_ag2` (34 tests) reste verte.

### Phase 9 — Garde-fous & audit
- Fail-loud partout où un `session_id`/`instance_id` manque au franchissement de
  frontière (jamais de trace « anonyme »).
- Vérifier qu'aucune clé n'atterrit dans une trace/JSON (R8) : le backend reste
  dans l'instance.
- `grep` anti-régression : aucun `backend` unique partagé restant dans les drivers.

### Phase 10 — Rollout, doc, mémoire
- Companion actionnable `2026-07-09-agent-instance-isolation-multisession-tracking.md`
  (checklist par phase).
- MAJ README/observability docs + mémoire projet (isolation par instance + session).

---

## Risques & décisions ouvertes

- **Passport = instance_id ?** À confirmer en Phase 1 (sinon introduire un
  `instance_id` dédié dérivé du passport).
- **Providers hétérogènes par instance** : autorisés et explicites, mais garder un
  garde-fou anti-fallback-silencieux (RETEX). Le tracker logge le provider effectif.
- **Coût console** : Phase 7 est un chantier front séparable ; les Phases 2–6+8
  (moteur + tracking) sont livrables sans la console.
- **AG2 & contexte privé** : AG2 garde déjà un `_oai_messages` par agent ; il suffit
  de ne plus partager le backend. À valider que le manager ne fuit pas le contexte
  entre agents (test d'isolation Phase 8).

## Découpage de livraison suggéré

1. **Lot moteur** (Phases 2–5, 8) : isolation par instance + tracking multi-session,
   testé offline. C'est le cœur de la demande.
2. **Lot persistence** (Phase 6) : colonnes + migration store.
3. **Lot console** (Phase 7) : vue multi-session.
