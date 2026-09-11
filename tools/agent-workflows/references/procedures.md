# Procédures conditionnelles de coordination

## Contradiction de conception

Identifier la question, les documents, leurs propriétaires et les dépendants.
Distinguer des périmètres compatibles d'une vraie contradiction. Le planner
responsable tranche selon l'objectif et les contraintes ; si ces contraintes
sont incompatibles, demander l'arbitrage utilisateur. Documenter la décision
canonique et marquer les décisions remplacées. Réévaluer les dépendants et leurs
tests. Une référence valide vers un document ne prouve pas sa mise en œuvre.

## Conflit de fusion

Préserver base commune et contributions. Confier la résolution à un contexte
neutre quand disponible. Préserver les intentions compatibles ; une opposition
sur le comportement retourne à la décision de conception. Vérifier le résultat
fusionné avec les tests applicables. Sans contexte neutre, annoncer la limite
et ne pas prétendre à un arbitrage indépendant. Aucun écrasement silencieux.

## Fichier volumineux

Mesurer la difficulté et appliquer les seuils du projet. Signaler les collisions
et responsabilités mélangées, organiser les éditions pour éviter la concurrence.
Si un découpage est requis, isoler un refactor sans changement de comportement,
préserver les interfaces et vérifier les appelants. Si aucune frontière cohérente
n'existe, revenir au planner. Aucun seuil universel 300/500, aucun gel automatique.
Un fichier suspendu pour refactor reste modifiable par le responsable du refactor.

## Évolution du cœur

Ne pas dupliquer le cœur pour éviter une évolution nécessaire. Proposer une
modification coordonnée avec ses dépendants, périmètre et tests. Un commentaire
ne suffit pas à autoriser une rupture d'interface ni un changement hors mandat.

## Outil mal compris

Examiner sa description, sa signature et des usages réellement observés.
Proposer une description clarifiée et évaluer avec des cas représentatifs,
y compris un contre-exemple. Ne modifier que les ressources maintenues dans le
périmètre autorisé ; ne pas changer le comportement de l'outil. Ne pas exercer
un outil à effets réels uniquement pour tester sa description sans autorisation.

## Revue et apprentissage

Choisir des regards complémentaires lorsque l'enjeu le justifie : contrat,
sécurité, comportement ou integration. Vérifier les findings contre le code actif.
Conserver les enseignements utiles dans les RETEX existants avec preuve et portée.
Un apprentissage local ne devient pas automatiquement une règle universelle.
