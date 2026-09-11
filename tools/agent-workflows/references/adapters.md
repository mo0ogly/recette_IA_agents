# Adaptation Claude et Codex

Le contrat décrit les missions, pas des noms d'outils universels.

- **Claude Code** : employer l'outil de délégation exposé dans la session. Un
  `subagent_type` personnalisé doit exister avant emploi ; sinon utiliser un
  agent disponible avec mission explicite. `run_in_background` n'est utilisable
  que si la signature courante le permet. Ne pas activer Agent Teams implicitement.
- **Codex** : employer les outils de collaboration réellement exposés et leurs
  limites courantes. Ne pas envoyer des paramètres Claude aux outils Codex.
- **Sans délégation** : exécuter les missions séquentiellement si le workflow
  l'autorise, consigner cette limitation et ne pas présenter une auto-revue
  comme indépendante. Ne pas lancer une autre CLI pour contourner une restriction.

Dans tous les cas, conserver objectif et preuves dans le handoff. Les workers
reçoivent les références pertinentes, pas une copie intégrale des conversations.
Le conducteur intègre le résultat, vérifie les preuves et applique OODA si nécessaire.

## Réutilisation dans un autre dépôt

Copier ensemble `tools/agent-workflows/` et les workflows que l'on souhaite
réutiliser, puis adapter leurs profils métier. Le noyau n'exige que Python 3.10+
pour le calculateur, sans dépendance externe, Bash ou lien symbolique obligatoire.
Les workflows métier complets ne deviennent pas génériques par cette copie.

Le chargement du contrat est explicite dans les skills/commandes modifiées : il
n'exige pas une nouvelle skill à invoquer. Pour une session Codex lisant ces
workflows, ouvrir le fichier de la skill ou commande demandé et suivre le même
contrat. Ce lot ne convertit pas automatiquement toutes les commandes Claude en
skills découvertes par Codex, ni n'installe une configuration utilisateur globale.

Conserver une seule source canonique du noyau par dépôt ; lors d'une mise à jour,
comparer les modifications locales avant remplacement. Les changements de sens
ou de barème exigent une nouvelle version et invalident les comparaisons concernées.

Pour transporter le Guide de terrain, copier aussi `.claude/field-guide/`,
rebrancher l’import CLAUDE.md et la lecture AGENTS.md, puis vérifier le budget.
Ne pas transporter automatiquement les apprentissages propres au métier source.
