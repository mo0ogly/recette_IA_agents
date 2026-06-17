# Principes et anti-patterns - Research Skill

## Principes fondamentaux

### Principe 1 : QUELQU'UN L'A DEJA FAIT

Avant de coder, TOUJOURS chercher sur internet. C'est une LOI, pas une suggestion.

Pour chaque probleme technique :
1. **WebSearch** : "[probleme] open source solution 2025 2026"
2. **GitHub** : repos, libs, exemples concrets
3. **API vendors** : doc officielle du produit/protocole
4. **Forums** : retours d'experience reels (SO, Reddit, HN)

Ce qu'on cherche :
- Un outil open-source qui fait deja le boulot → integrer plutot que recoder
- Une crate Rust (ou un module Python/lib React) → utiliser
- Un pattern valide par d'autres → s'en inspirer
- Des retours d'echec → eviter les memes pieges

### Principe 2 : ZERO MOCK, ZERO PLACEHOLDER, ZERO INVENTION

- Donnees reelles, sources verifiables, URLs qui existent
- Code qui compile et s'execute
- Commits, endpoints, fichiers qui existent reellement

### Principe 3 : "JE NE SAIS PAS FAIRE" N'EXISTE PAS

Avant de declarer impossible :
1. Chercher sur internet (Principe 1)
2. Approche alternative (B, C, D, E, F...)
3. Decomposer en sous-problemes
4. Verifier versions/dependances
5. Reduire le scope (80% > 0%)
6. Workaround
7. Reformuler le probleme
8. **Seulement apres** : expliquer pourquoi + proposer alternative

### Principe 4 : CHAQUE RECHERCHE ENRICHIT LE REFERENTIEL

Toute recherche, test, echec, decouverte → fichier dans le referentiel.
Un resultat negatif a de la valeur : il evite de re-essayer.

### Principe 5 : L'EXISTANT D'ABORD

Avant de concevoir un composant, mapper TOUT ce qu'on a deja.

L'existant inspect_ia_agents a deja :
- Le modele canonique `AgentActionEvent` (event_id, agent_id, policy_decision, approval_state...)
- Le trait `EventStore` + `SqliteEventStore` (append-only, hash chain, replay deterministe I4)
- La gateway Axum + Control/Data/Audit Plane, les proxies d'effets de bord (I5)
- Le harness Python `recette/` (corpus, juge 4 dimensions, lab mock) ; la console React `console/`
- Le moteur de discovery Rust+eBPF `discoveryprobe/`

**INTERDIT de recreer** un trait de persistance ou un evaluateur de policy si `src/` en a deja un.

### Principe 6 : ETUDIER LES GAPS, PAS SEULEMENT LES FEATURES

Apres avoir compris les outils existants :
1. Chercher ce que les UTILISATEURS disent manquer
2. Chercher les benchmarks de precision (accuracy, false positives)
3. Identifier les evolutions demandees par la communaute
4. Croiser avec le besoin specifique du projet (gouvernance/recette d'agents IA, pas le cas d'usage generique de l'outil)

---

## Anti-patterns observes

| Anti-pattern | Exemple | Correction |
|-------------|---------|------------|
| Affirmer sans verifier | "1M tokens n'existe pas chez Anthropic" | WebSearch AVANT de repondre |
| Sauter a l'implementation | Ecrire des structs Rust en Phase 1 | Respecter les gates |
| Designer sans mapper l'existant | Nouveau trait sans verifier `src/` | Phase 0 obligatoire |
| Oublier les gaps utilisateurs | Concevoir sans chercher les demandes des users | Phase 2 obligatoire |
| Documenter a la fin | Ecrire la doc apres avoir code | Doc au fil de l'eau (Regle 3) |
| Repondre de memoire | Donner des prix sans verifier | Internet d'abord (Regle 1) |
| Ne pas garder de preuves | Recherche sans sauver les resultats | Chaque decouverte → fichier |
| Claim de completion sans preuve | "Les tests passent" sans avoir lance les tests | Verification avant claim |
| Sauter une phase "pour gagner du temps" | Passer de Phase 1 a Phase 3 | Iron Law : gate = livrable |
| Implementer Option B apres avoir choisi A | Oublier les decisions de RESEARCH_LOG | Lire les [DECISION] tags |
