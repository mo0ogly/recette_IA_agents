# Scoring, progression et gates — méthode 2

## Contrat d'évaluation

Avant exécution, inventorier les critères acceptés et les contrôles applicables.
Figer leurs identifiants, domaines, poids, pénalités et gates ; un changement de
barème retourne au plan. Ne pas retirer un contrôle échoué pour rendre le score vert.
Conserver l'inventaire et les observations dans `workflow-evidence.json` à côté du
rapport du workflow. Pour KS : `docs/reviews/<id>.evidence.json` ; pour PDCA :
`cycle_NNN/C_WORKFLOW_EVIDENCE.json` ; pour APEX : dossier de session si sauvegardé,
sinon dossier temporaire explicitement indiqué et conservé jusqu'à la revue.

Format JSON accepté par `evaluate.py` :

- `method_version`: chaîne `"2"` ; `scope_id`: identifiant stable du périmètre.
- `artifacts`: objet chemin relatif → SHA-256 des fichiers évalués, y compris
  plan validé, sources concernées et preuves. Les fichiers doivent être contenus
  dans la racine passée à `--root`. Inclure tous les fichiers du périmètre et
  documenter la liste : le programme ne peut pas détecter un fichier omis.
- `domains`: objet nom → poids positif. Conserver les poids du profil ; les
  domaines sans contrôle applicable sont exclus de la moyenne.
- `checks`: liste non vide d'objets avec `id`, `domain` (nom ou `null` pour une
  activité de gate), `mandatory` (booléen), `gate` (`entry`, `validation`,
  `delivery`), `penalty` (points par occurrence), `max_penalty` et `severity`
  (`none`, `minor`, `major`, `critical`). Sévérité major = HAUTE dans Wattson.
- `results`: observations `{id, status, count, evidence}`. `status` vaut `PASS`,
  `FAIL`, `PARTIEL`, `NON TESTÉ` ou `NON APPLICABLE`. `count` est le nombre
  mesuré d'occurrences, nul pour PASS/NA, strictement positif pour FAIL.
  `evidence` liste des fichiers inspectables. PASS/FAIL exigent une preuve.
  NA exige `reason`, une justification examinée en revue. Un résultat absent
  devient NON TESTÉ. Aucun résultat ne peut remplacer le barème du contrôle.

Un ratio peut être fourni comme `count` entre 0 et 1 avec sa mesure numérateur /
dénominateur dans la preuve et sa pénalité maximale configurée. Ne jamais évaluer
une formule de configuration avec `eval`. Un barème ancien textuel non traduisible
sans choix métier exige une décision explicite avant scoring, jamais une note
inventée. Les jeux de tests synthétiques du calculateur ne sont pas des preuves
sur l'application auditée.

## Calcul

Domaine = `max(0, 100 - somme(min(count * penalty, max_penalty)))` sur les FAIL.
Qualité = moyenne des domaines applicables pondérée par leurs poids normalisés.
Un domaine contenant un contrôle PARTIEL/NON TESTÉ rend le score provisoire :
ce nombre ne peut pas autoriser la livraison. Aucun domaine applicable = score
indisponible. La moyenne n'est pas une mesure de confiance ou de probabilité.

Progression = critères PASS de la phase / critères applicables de la phase.
PARTIEL et FAIL ne comptent pas comme réalisés. L'entrée ne compte pas les
contrôles futurs ; validation inclut entry + validation ; delivery inclut tout.
Aucun critère applicable = progression indisponible, pas 100 %.

## Passage et finalisation

- `entry` : prérequis et plan nécessaires validés ; gates futures non exigées.
- `validation` : contrôles obligatoires de la phase et d'entrée PASS.
- `delivery` : tous les contrôles obligatoires PASS, aucun FAIL major/critical,
  qualité finale >= 70 et aucun domaine applicable < 50.
- `audit` : toutes les observations applicables terminales PASS/FAIL, activités
  obligatoires (domain null) PASS. Un audit complet peut conclure à une mauvaise
  qualité ; `allowed` pour audit ne vaut jamais `ship_allowed`.

Les niveaux qualité restent OK >= 80, WARN >= 70, BLOQUÉ >= 50, STOP < 50.
Une gate bloquante prime toujours sur le niveau qualité. Un score de 94 avec un
finding majeur reste bloquant. Les exigences plus strictes du projet restent
applicables ; un score n'accorde pas de permission d'écriture ou de déploiement.

Chaque finding majeur ou critique ouvert doit figurer dans l'inventaire comme
contrôle échoué. Les preuves doivent correspondre au niveau de frontière exigé :
un grep ou un import ne remplace pas une recette comportementale.

## Utilisation et verdict KS

Depuis la racine du projet contenant `tools/` :

```sh
python3 tools/agent-workflows/evaluate.py docs/reviews/STORY.evidence.json --root . --phase delivery
```

Remplacer STORY par l'identifiant réel. Sortie JSON sur stdout ; code 0 = gate
passée, 1 = bloquée, 2 = entrée invalide ou preuve/fichier absent/périmé. Les deux
derniers interdisent le passage. Conserver la sortie à côté de l'entrée, sans
inclure la sortie dans les empreintes de cette même entrée (pas d'autoréférence).

`ks-review` termine avec `Max severity: ...` et `Ship allowed: yes|no`, dérivés du
résultat delivery courant, jamais de la seule moyenne. `ks-ship` recalcule la
gate à partir de l'entrée et vérifie les empreintes avant toute livraison. Il
exige aussi le verdict textuel de revue : une ancienne ligne verte seule ne suffit pas.

Un échec déclenche OODA : observation de la cause, orientation sur l'objectif,
décision de correction ou replanification, action et nouvelle preuve. Mettre à
jour les empreintes seulement après les contrôles sur le nouveau livrable.

## Comparabilité

`--previous` accepte une ancienne sortie du calculateur. Le delta n'est fourni
que pour deux scores finaux de même méthode, périmètre, phase, configuration et
ensemble de contrôles applicables. Un rapport historique ou incomplet donne un
delta null. Conserver les fichiers historiques. La méthode 2 ne multiplie jamais
la qualité par 0.8 en mode local : rapporter plutôt sa progression et ses limites.

## Limites de confiance

Ce programme valide des déclarations structurées, l'existence des preuves et les
empreintes, pas la véracité de leur contenu ni l'exhaustivité du périmètre. Une
revue confronte les observations aux critères, au code et aux exécutions réelles.
Il ne constitue ni un sandbox, ni un système de reprise, ni un moteur de campagne.
