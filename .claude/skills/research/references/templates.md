# Templates de documentation - Research Skill

Utiliser avec `/research update [topic] [etat] [nom]`

---

## Template VALIDATED

```markdown
# [VALIDATED] {Nom}

**Date :** {date}
**Fichier(s) :** {fichier.rs / .py / .tsx ou autre artefact}
**Commit :** {hash complet}
**Preuve :** {test passe / build OK / endpoint repond / lab valide}

## Ce qui fonctionne
{description concrete}

## Limites connues
{ce qui ne marche pas encore}

## Prochaine etape
{quoi faire dessus}

## Recherches Internet effectuees
- Query : "{termes exacts}" -> {resultats} ({URL})

## Preuves conservees
- {description} -> {chemin ou URL}
```

---

## Template INVESTIGATED

```markdown
# [INVESTIGATED] {Nom}

**Date :** {date}
**Status :** Explore, resultats partiels
**Phase :** {0-6} - {nom de la phase}

## Recherches Internet effectuees
- Query : "{termes exacts}" -> {resultats} ({URL})

## Ce qu'on a trouve
{resultats}

## Ce qui manque
{gaps identifies}

## Preuves conservees
- {fichier ou URL de preuve}

## Questions ouvertes
{liste de questions}

## Prochaine action recommandee
{action concrete et mesurable}
```

---

## Template ABANDONED

```markdown
# [ABANDONED] {Nom}

**Date d'abandon :** {date}
**Fichiers supprimes/desactives :** {liste ou "aucun"}

## Ce que c'etait
{description de ce qu'on a essaye}

## Pourquoi abandonne
1. {raison 1 - concrete}
2. {raison 2}

## Ce qui le remplace
{alternative adoptee ou "rien - besoin abandonne"}

## NE PAS RE-ESSAYER sans avoir lu ceci
{conditions minimales si quelqu'un veut retenter a l'avenir}
```

---

## Template BACKLOG

```markdown
# [BACKLOG] {Nom}

**Priorite :** CRITIQUE | HAUTE | MOYENNE | BASSE
**Phase de demarrage :** {0-6}
**Status :** NOT-STARTED
**Effort estime :** {N jours/semaines}

## Perimetre
{ce qu'on veut faire - concret}

## Pistes d'investigation
- A) {approche A} - Pros: {X} | Cons: {Y}
- B) {approche B} - Pros: {X} | Cons: {Y}

## Blocages identifies
{ce qui empeche de commencer aujourd'hui}

## Prerequis avant de demarrer
{liste des conditions}
```
