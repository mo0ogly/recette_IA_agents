# discovery/INDEX.md - Mise a jour pour cloture COUCHE 5

**Fichier cible :** `_alire/research_discovery/discovery/INDEX.md`

---

## Section VALIDATED - Ligne a ajouter

Dans le tableau "VALIDATED (fonctionne, avec preuve)", ajouter apres la ligne "Discovery Lab" :

```markdown
| **COUCHE 5 Banner-server** (30 banners 9001-9030, 30/30 detection LiaProbe, 30 PROBE JSON recette, skill /create-banner v2.2) | `docker/discovery-lab/recette/`, `docker/discovery-lab/banner_analysis/`, `.claude/skills/create-banner/SKILL.md` | 2026-03-02 |
```

---

## Section BACKLOG - Mise a jour ligne Discovery Lab

La ligne "~~Simulation Lab~~" dans le BACKLOG est deja marquee VALIDATED.
Ajouter une nouvelle ligne backlog pour ce qui reste de la COUCHE 5 :

```markdown
| Skill /recette-banner v2 (nouveau format PROBE JSON avec verdict + liaprobe_taxonomy) | BASSE | Backlog | Non demarre |
```

---

## Status global a mettre a jour

Ligne 5 du fichier (Status global) :

Avant :
```
**Status global :** VALIDATED - LiaProbe scanner autonome operationnel. 7563 patterns actifs (commits d0ba5ebdfb + 867d2d780e + f3a78163e4 + 79cff8c8b9 + 0a8130d468, 2026-02-28/03-01)
```

Apres :
```
**Status global :** VALIDATED - LiaProbe scanner autonome operationnel. 15 719 patterns actifs. COUCHE 5 banner-server : 30/30 banners detectes (scans #145 + #148). Commits cles : 3b82e8bfe5 (30/30 detection) + 8eae40d4b2 (30 PROBE JSON recette) + e1ec663fb5 (skill /create-banner v2.2). Derniere MAJ : 2026-03-02.
```

---

## Chiffres mis a jour

- Validated : 13 -> 14 (ajout COUCHE 5 banner-server)
- Investigated : inchange (11 elements)
- Abandoned : inchange (1 : WMI)
- Backlog : inchange (existant) + 1 (skill /recette-banner v2)
