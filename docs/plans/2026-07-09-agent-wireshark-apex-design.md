# APEX — « Wireshark pour agents IA » (analyseur d'observabilité défensive)

**Date** : 2026-07-09
**Cadre** : recette DÉFENSIVE — dissection/filtrage/statistiques/audit sur des flux de
recette et un corpus ground-truth (R23). Aucune génération de contenu offensif : l'outil
LIT et EXPLIQUE des échanges déjà capturés (legibility-first, I1). C'est un analyseur de
protocole, pas un générateur d'attaque.
**Statut** : PLAN (à valider)

## Objectif

Passer de « un panneau de flux wire enrichi » à un **vrai analyseur type Wireshark pour
communications d'agents IA** : capture live, langage de display-filter, dissecteurs de
protocole empilés (L3/L4 → L8 sémantique), follow-stream, expert-info, statistiques,
format de capture portable — le tout **tracké** de bout en bout (session/instance, chaîne
de reçus content-free I1) et **connecté à Lux** (le cockpit).

## Acquis (à ne pas refaire)

| Brique | Fichier | Rôle Wireshark équivalent |
|---|---|---|
| Décodage en couches L3/L4, TLS/JA3, HTTP, timing | `console/.../wireLayers.ts`, `WireLayersView.tsx` | « packet details » par couche |
| Dissecteur sémantique L8 (messages/tools/tokens) | `wireLlmDecode.ts` | dissecteur de protocole applicatif |
| Ladder run (DECIDE→DO) | `wireRunTimeline.ts` | « Flow graph » |
| Export JSONL / HAR / curl | `proxyExport.ts`, `curl.ts` | export pcap / « Copy as cURL » |
| Tracking session/instance + reçus chaînés | `recette/tracking.py`, store `session_id`/`instance_id` | annotation + intégrité de séquence |
| Graphe d'interaction + PageRank | `recette/orchestration_graph.py` | statistiques de conversation |
| Delta-poll 1 s | `useDeltaFeed.ts`, `wireDeltaClient.ts` | capture (mais pas encore live) |

## Écarts vs un vrai Wireshark (ce que le plan comble)

1. **Capture LIVE** (temps réel), pas un poll 1 s.
2. **Display-filter DSL** (grammaire de filtre composable sur tous les champs L3–L8).
3. **Registre de dissecteurs** pluggable (une couche = un dissecteur déclaré).
4. **Follow-stream / Follow-agent-turn** (reconstruction d'une conversation complète).
5. **Expert-info** (signaux d'observabilité : secret en clair dans un body, dérive JA3
   intra-session, appel d'outil hors scope déclaré, endpoint inattendu) — **contre le
   ground-truth déclaré**, pas des heuristiques d'attaque.
6. **Statistiques** (hiérarchie de protocole, hiérarchie d'endpoints, throughput I/O,
   comptabilité tokens/coût).
7. **Format de capture portable** `.agentpcap` (chaîné par hash, importable/rejouable).
8. **Coloring rules + vues sauvegardées** (deep-linkables).
9. **Connexion orchestration → Lux** (dette de la règle « pas de backend sans Lux »).

---

## Plan APEX (10 phases)

### Phase 1 — Cadrage & modèle de dissection
- Formaliser la pile en dissecteurs déclarés : `L3L4 → TLS → HTTP → L8(LLM sémantique)`.
- Contrat `Dissector`: `(flow, ctx) -> DissectNode[]` pur/déterministe (I4). Le L8 réutilise
  `decodeLlmFlow`. Livrable : types + registre, pas d'UI.

### Phase 2 — Capture LIVE (temps réel)
- Backend : endpoint SSE `GET /proxy/wire/stream` (nouvelle route, réutilise le realtime
  transport `platform/realtime`) émettant chaque flux à l'insertion.
- Front : `useWireStream` (hook SSE) remplaçant/complétant le delta-poll ; bascule
  « live / pause » (comme Wireshark start/stop). Rétro-compat : le poll reste le fallback.
- Tracking : chaque event porte `seq`/`session_id`/`instance_id` (déjà en place).

### Phase 3 — Display-filter DSL
- Grammaire composable façon Wireshark : `tls.ja3 == d41d8… && http.status >= 400`,
  `l8.tool == "delete_repo"`, `instance == "attacker" && session == "s1"`.
- Parseur pur `wireFilter.ts` (tokenizer → AST → prédicat) sur les champs L3–L8 dissequés.
  Champs adressables par chemin (`l3l4.dst_port`, `l8.tokens.total`, `timing.ttfb_ms`).
- Côté back : traduction du sous-ensemble « champs indexés » en SQL (host/status/session/
  instance/method) ; le reste filtré client sur le buffer. Tests unitaires du parseur.

### Phase 4 — Follow-agent-turn (follow-stream)
- Reconstruction d'une conversation : regrouper les flux par `(session_id, instance_id)` et
  ordonner par `seq` → transcript L8 complet (system/messages/tool_calls/answers/tokens),
  avec la ladder DECIDE→DO alignée. Généralise `wireRunTimeline` + `runConversation`.
- UI : « Suivre le tour de l'agent » depuis un flux sélectionné (comme Follow TCP Stream).

### Phase 5 — Expert-info (signaux d'observabilité, défensif)
- Panneau de signaux calculés PUREMENT sur le flux + le ground-truth déclaré :
  - secret en clair non masqué dans un body (regex clés) → `warn`,
  - dérive JA3 intra-session (empreinte TLS qui change pour une même instance) → `note`,
  - appel d'outil hors du scope déclaré de l'instance (via la team/manifest) → `error`,
  - endpoint contacté hors allowlist `provider_host` → `warn`.
- **Cadre** : ce sont des écarts vs ce qui est DÉCLARÉ (audit de conformité), pas de la
  détection d'attaque. Réutilise `judge_orchestration`/`admission` côté back.

### Phase 6 — Statistiques
- `wireStats.ts` (pur) : hiérarchie de protocole (part L3/L4/TLS/HTTP/L8), top endpoints,
  throughput I/O par fenêtre, comptabilité **tokens/coût** par instance/session/modèle.
- UI : onglet « Statistiques » (tableaux + barres, thème tokens only — Lux).

### Phase 7 — Format de capture portable `.agentpcap`
- Sérialisation d'une sélection de flux + leurs reçus content-free chaînés (I1) + le
  ground-truth → un fichier importable/rejouable hors-ligne (déterministe).
- Réutilise `context_receipt.chain_receipts` + `freeze_to_corpus`. Import → rejoue dans le
  panneau sans backend live. Équivalent d'un pcap partageable pour un auditeur RSSI.

### Phase 8 — Coloring rules + vues sauvegardées
- Règles de coloration par prédicat display-filter (ex. `http.status >= 400` → rouge).
- Vues sauvegardées = filtre + colonnes + coloration, deep-linkables (URL), comme les
  profils Wireshark. Pur front, persistées dans l'URL / le store console.

### Phase 9 — Connexion orchestration → Lux (dette « pas de backend sans Lux »)
- Route `recette/api/routers/orchestrate.py` : `POST /orchestrate/run` (team + provider/model
  par instance via `build_llm`, `SessionTracker` partagé en app-state) + `GET /orchestrate/
  sessions[/{id}]` (reçus + verify + graphe). Panneau console reliant instance → ses flux
  wire (deep-link WirePanel filtré). L'orchestrateur cesse d'être « dark ».

### Phase 10 — Tests, doc, rollout
- Tests : parseur filtre, dissecteurs, stats, follow-stream, agentpcap round-trip, SSE.
- Doc utilisateur (analyste SOC/RSSI) + companion actionnable + mémoire.
- Garde-fous : tout ≤ 800 lignes (extraction en modules), `tsc` propre, suite verte.

---

## Tracking de bout en bout (exigence explicite)

Chaque flux, signal, statistique et entrée `.agentpcap` porte `session_id` + `instance_id`
et s'inscrit dans la chaîne de reçus content-free par session (I1). Un run d'orchestration
(Phase 9) alimente la même chaîne → un analyste suit **une instance à travers ses sessions**
depuis la capture live jusqu'à la stat agrégée, avec intégrité de séquence vérifiable.

## Découpage de livraison suggéré (incréments sûrs)

1. **Lot dissection+filtre** (Phases 1, 3) : le cœur « Wireshark » (registre + display-filter),
   pur/testable, sans infra.
2. **Lot live+follow** (Phases 2, 4) : capture temps réel + follow-agent-turn.
3. **Lot analyse** (Phases 5, 6) : expert-info défensif + statistiques.
4. **Lot portabilité+Lux** (Phases 7, 9) : `.agentpcap` + connexion orchestration à Lux.
5. **Lot finition** (Phases 8, 10) : coloration/vues + tests/doc.

Recommandation : commencer par le **Lot dissection+filtre** — c'est ce qui transforme le
panneau en analyseur, entièrement en front pur et testable, zéro risque infra.
