# Agentic Traceability -- Decision Log & Plan Persistence

Tracking du projet dans `docs/tracking/` (a la racine du repo, cree au besoin).
Ne PAS eparpiller de fichiers de suivi a la racine du projet.

## `docs/tracking/` est GITIGNORE -- jamais committe (R25)

`docs/tracking/` est dans `.gitignore` : tout artefact de suivi d'agent (PDCA,
APEX, `PLAN_*.md`, `decision_log.jsonl`, RETEX, TODO, sorties de boucle, scratch
de tache) y vit et n'est **jamais committe ni pousse**. Raison : ce repo est un
CORPUS ground-truth + son harnais de recette ; la trace de travail d'un agent
n'est pas un livrable, elle ne doit ni polluer le corpus ni gonfler l'historique
git. Regles fermes :

- Ecrire le suivi UNIQUEMENT sous `docs/tracking/` (jamais a la racine, ni dans
  `recette/`, `corpus/`, `console/`).
- JAMAIS `git add` / `git add -f` un fichier de tracking. S'il apparait dans
  `git status`, il doit rester untracked (ou etre couvert par `.gitignore`).
- Un livrable DURABLE (doc produit, runbook, ADR officiel) va dans `docs/`
  committe -- pas dans `docs/tracking/`. Le suivi ephemere reste gitignore.
- Les sorties de tache ephemeres du harnais (ex. `/tmp/.../tasks/*.output`) sont
  hors repo et auto-nettoyees : ne jamais les recopier dans le repo.

## Gitignore != jetable -- ne JAMAIS perdre le tracking

`docs/tracking/` n'est PAS sauve par git : c'est la **memoire de travail** locale
de l'operateur (PDCA/APEX/plans/RETEX/decision log). Consequence directe :

- Un agent ne DOIT JAMAIS `rm`, `git clean`, ecraser ou tronquer un fichier de
  `docs/tracking/`. Une suppression n'est PAS recuperable via git (le fichier
  n'y est pas) -- c'est une perte definitive.
- On AJOUTE au tracking, on ne le purge jamais "pour faire propre".
- Si un fichier de `docs/tracking/` apparait absent ou vide, NE PAS le recreer a
  l'aveugle : verifier d'abord un backup local hors repo
  (`~/recette_tracking_backups/*.tgz`) ou un commit dangling pre-squash
  (`git log --all -- 'docs/tracking/*'`, `git fsck --lost-found`).
- Sauvegarde recommandee hors repo (anti-perte, hors git) :
  `tar czf ~/recette_tracking_backups/tracking_$(date +%Y%m%d).tgz -C docs tracking`.

## Decision Log (pour decisions non-triviales)

Fichier : `docs/tracking/decision_log.jsonl`

### Quand ecrire une entree
- Choix d'architecture (nouveau plane, nouveau trait, nouveau sujet NATS, schema d'evenement).
- Replanification (plan A echoue -> plan B).
- Rejet d'une approche (et pourquoi).
- Choix touchant un invariant (I1-I6) ou un failure mode.
- Tout choix impactant plus de 3 fichiers.

### Format JSONL (1 ligne = 1 decision)

```json
{"timestamp":"ISO8601","session":"nom-court","action":"VERBE_COURT","reasoning":"pourquoi","alternatives_rejected":["B rejetee car..."],"invariants_touched":["I1","I4"],"outcome":"resultat","confidence":"high|medium|low","plan_ref":"docs/tracking/PLAN_*.md ou null"}
```

### Ce qu'on NE trace PAS
- Decisions triviales (formatage, renommage simple).
- Actions mecaniques (build, test, commit) -- deja dans git log.

## Plans Persistants (pour taches multi-etapes)

Repertoire : `docs/tracking/PLAN_*.md`. Nommage : `PLAN_{TASK}_{YYYY-MM-DD}.md`.

```markdown
# Plan : {TITRE}
Date : {YYYY-MM-DD}
Status : EN_COURS | TERMINE | ABANDONNE | REPLANIFIE
Invariants concernes : I1..I6 (lister)

## Objectif
{1-2 phrases}

## Etapes
- [ ] Etape 1
- [ ] Etape 2

## Decisions prises
- {decision} -> {raison}

## Ecarts et replanification
- {ecart} -> {ajustement}

## Resultat
{bilan final}
```

### Mise a jour
- Cocher les etapes au fil de l'eau (`[x]`).
- Replanification : Status -> REPLANIFIE, nouveau plan avec lien.
- Abandon : Status -> ABANDONNE + raison.

## Skill /replan

Quand un plan derive : observer l'etat reel (fichiers, build, tests), comparer au plan,
identifier les ecarts, produire un plan ajuste.
