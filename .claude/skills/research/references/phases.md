# Phases detaillees - Research Skill

## PHASE 0 : Etude de l'existant interne

**Quoi :** Lire TOUT le code existant dans le codebase qui touche au sujet.

**Livrable :** `{topic}/investigated/YYYY-MM-DD_mapping-existant.md` contenant :
- Liste de TOUTES les fonctions/structs/types existants lies au sujet
- Pour chaque element : nom, fichier, ligne, role, reutilisable (HAVE/ADAPT/NON)
- Matrice HAVE / ADAPT / NEED finale

**Gate :** Le fichier existe ET a ete presente a l'utilisateur.

Zones moteur inspect_ia_agents a verifier en priorite (via Glob pour confirmer existence) :
- `src/` + `cmd/*` : gateway Axum, Control/Data/Audit Plane (Rust)
- `src/` : trait `EventStore` + impl (`SqliteEventStore`), modele canonique `AgentActionEvent`
- `discoveryprobe/` : moteur de discovery Rust + eBPF (common/ebpf/loader/broker)
- `recette/` : harness Python (corpus, juge 4 dimensions, lab) ; console `console/`

---

## PHASE 1 : Recherche externe

**Quoi :** Etudier comment les autres font. Lire leur CODE SOURCE, pas leur marketing.

**Methode :**
1. WebSearch : "[probleme] open source solution 2025 2026"
2. GitHub : chercher repos, libs, exemples concrets
3. API vendors : doc officielle du produit/protocole
4. Stack Overflow / forums : retours d'experience reels

**Livrable :** `{topic}/investigated/YYYY-MM-DD_{sujet}-recherche.md` contenant :
- Pour chaque outil etudie : structure donnees, moteur matching, mecanisme MAJ, limites
- Queries de recherche exactes
- URLs des sources
- Ce qu'on prend, ce qu'on rejette, POURQUOI

**Gate :** Le fichier existe ET couvre au minimum 3 solutions existantes.

---

## PHASE 2 : Analyse des gaps

**Quoi :** Ce que les UTILISATEURS disent manquer. Pas ce qu'on pense -- ce qu'ILS disent.

**Methode :**
1. WebSearch : "{outil} limitations" / "{outil} missing features" / "{outil} feature request"
2. GitHub Issues : filtrer "enhancement", "feature request"
3. Forums (Reddit, HackerNews, SO) : retours reels
4. Croiser avec le besoin specifique du projet (gouvernance/recette d'agents IA, pas le cas d'usage generique de l'outil)

**Livrable :** `{topic}/investigated/YYYY-MM-DD_{sujet}-gaps.md` contenant :
- Gaps identifies par les utilisateurs (avec sources)
- Gaps specifiques au besoin inspect_ia_agents (recette/discovery/audit d'agents)
- Comment notre solution adresse (ou non) chaque gap

**Gate :** Le fichier existe ET contient au moins 5 gaps documentes avec sources.

---

## PHASE 3 : Conception

**Quoi :** Concevoir l'architecture EN REUTILISANT le maximum de l'existant.

**Regles :**
- Partir de la matrice HAVE/ADAPT/NEED de Phase 0
- Chaque composant "NEED" doit etre justifie : pourquoi on ne peut pas ADAPTER ?
- Chaque decision cite la preuve de Phase 1 ou 2 qui la justifie

**Livrable :** `{topic}/investigated/YYYY-MM-DD_{sujet}-conception.md` contenant :
- Architecture proposee avec schema
- Decisions avec justifications tracees (lien Phase 1/2)
- Matrice de reutilisation (tel quel / adapte / nouveau)

**Gate :** Le fichier existe ET l'utilisateur a valide la conception.

---

## PHASE 4 : Plan de dev

**Quoi :** Detailler les etapes d'implementation avec criteres d'acceptance.

**Livrable :** `{topic}/investigated/YYYY-MM-DD_{sujet}-devplan.md`

Contenu minimum :
- Liste d'etapes numerotees avec fichiers a modifier
- Critere d'acceptance pour chaque etape
- Estimation d'effort
- Ordre de priorite

**Gate :** Le fichier existe ET l'utilisateur a valide le plan.

---

## PHASE 5 : Implementation

**Quoi :** Coder, tester, valider.

**Regles inspect_ia_agents (R3) :**
1. 1 fichier → Test → Validation utilisateur → Generalisation
2. JAMAIS de modifications en masse sans test individuel prealable
3. Commit AVANT chaque etape risquee

**Verification avant chaque claim de completion :**
```
AVANT de dire "c'est fait" ou "les tests passent" :
1. Identifier la commande qui prouve le claim
2. Executer la commande (fraiche, complete)
3. Lire le output + code de sortie
4. SEULEMENT si output confirme : faire le claim
```

**Gate :** Code compile, tests passent, lab valide.

---

## PHASE 6 : Documentation finale

**Quoi :** Compiler les fichiers de recherche en documentation finale propre.

**La doc finale est une COMPILATION, pas une reecriture.** Tout est deja documente dans les phases. Phase 6 organise et relie.

**Livrable :**
- Referentiel mis a jour (INDEX.md, RESEARCH_INDEX.md, RESEARCH_LOG.md)
- Status du topic passe a VALIDATED (avec preuve)
- Eventuellement : SKILL.md mis a jour si le topic implique une nouvelle skill

**Gate :** Referentiel mis a jour, status VALIDATED avec preuve.
