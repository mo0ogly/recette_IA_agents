# Contrat commun de coordination — version 2

Ce contrat est intégré à APEX, audit-PDCA et KS. Le lire à leur démarrage et
transmettre les paragraphes utiles aux agents délégués. Il ne lance aucun
processus, ne donne aucune permission et ne remplace pas le workflow choisi.

## Pilotage et délégation

Un seul conducteur possède l'objectif. Un workflow appelé travaille sur une
mission bornée, sans relancer un cycle concurrent. Une délégation contient :
objectif, critères observables, périmètre autorisé, dépendances, décisions déjà
prises, ressources utiles, livrable attendu et preuves à rapporter.

Le planner arbitre les questions transverses ; le worker choisit les détails
locaux compatibles. Il remonte toute découverte invalidant l'objectif, une
interface partagée ou une dépendance. Les tâches couplées sont ordonnées ; seules
les missions indépendantes sont parallélisées, dans les limites réellement
exposées. Ne pas multiplier les agents pour une tâche simple.

Adapter les appels avec [adapters.md](references/adapters.md). Préserver les modes
APEX `--economy` et PDCA `--mode=local`. Une permission absente ne devient pas
présente parce que le contrat mentionne une délégation ou une livraison.

## Boucles OODA intégrées

Au démarrage, au retour significatif d'un agent, à une contradiction, à une gate
échouée ou à une évolution du contexte :

1. **Observer** les faits, résultats, état courant et preuves manquantes.
2. **Orienter** selon l'objectif, les critères acceptés, les dépendances et les
   décisions applicables ; distinguer preuve, hypothèse et contradiction.
3. **Décider** : poursuivre, collecter une preuve, corriger, redécouper, revenir
   au plan ou signaler le blocage. Nommer le responsable et le résultat attendu.
4. **Agir** dans le périmètre autorisé, puis observer l'effet avant de conclure.

Utiliser les rapports existants, avec une trace courte : événement/preuve,
interprétation utile, décision motivée, responsable, action, résultat observé et
prochaine vérification. Ne pas demander de transcription du raisonnement privé,
ni produire une ligne OODA pour chaque appel d'outil.

Un échec répété sans nouvelle preuve impose une réorientation ; ne pas refaire
la même tentative. Conserver les limites du workflow appelant (KS : deux boucles
de correction maximum). Un changement d'intention retourne au plan. Une limite
de ressources atteinte devient un blocage explicite, jamais un succès.

## Gates, scores et preuves

Appliquer [scoring.md](references/scoring.md) à la planification des critères et
à chaque gate. Qualité et progression sont distinctes. Une preuve obligatoire
manquante n'est jamais compensée par un bon score moyen. Une gate verte ne vaut
ni autorisation de livrer ni preuve que le déploiement a eu lieu.

Une revue indépendante vérifie l'exhaustivité de l'inventaire et la pertinence
des preuves ; le calculateur vérifie seulement les données fournies. Sans revue
indépendante, annoncer cette limite, garder les mêmes critères de validation.

## Procédures conditionnelles

Lire [procedures.md](references/procedures.md) uniquement lors d'un conflit de
conception, d'une fusion, d'un fichier difficile à modifier ou d'un outil mal
compris. Aucun gel automatique ni réparation de conception par compilation
n'est fourni. Les limites de taille du projet priment sur des seuils génériques.

## Profil projet

Appliquer [le profil local](references/project.md) en plus des gates communes.
Conserver les autorisations et exigences métier du dépôt ; aucune convention
Wattson n'est imposée par ce noyau. Les contraintes locales plus strictes restent
bloquantes même avec un score global satisfaisant.

## Sources et limites

- [Cursor, février 2026](https://cursor.com/blog/self-driving-codebases) :
  séparation des rôles, ownership, handoff et retours vers le planner.
- [Cursor, juillet 2026](https://cursor.com/blog/agent-swarm-model-economics) :
  contradictions de design, arbitrage neutre, fichiers volumineux, revues et
  mémoire partagée. Son VCS et ses mécanismes d'exécution ne sont pas reproduits.
- [Anthropic, juin 2025](https://www.anthropic.com/engineering/multi-agent-research-system) :
  délégations précises, effort adapté et ergonomie des outils. Aucun facteur de
  coût de cette expérience n'est une prévision pour ces workflows.
- [Air University, OODA de Boyd](https://www.airuniversity.af.edu/AFCLC/News/Article-Display/Article/1777083/cultural-ksas-skill-development-using-the-ooda-loop/) :
  observer, orienter, décider, agir. L'intégration aux gates est notre adaptation,
  pas une prescription de Cursor.

Origine des procédures : package `swarm-module` fourni par l'utilisateur,
version septembre 2026. Contrat, scoring et contrôles présents : version 2 locale.

## Stigmergie : Guide de terrain

Lire [l’index partagé](../../.claude/field-guide/index.md) au démarrage.
Le conducteur fournit son contenu courant aux agents délégués, avec les notes
pertinentes ; chaque agent peut proposer ou effectuer une mise à jour autorisée.
Capturer les rencontres surprenantes vérifiées, pas un compte rendu exhaustif.
Respecter le budget de lignes et contrôler le guide après modification avec
`python3 tools/agent-workflows/check_guide.py`. Une connaissance invalidée est
corrigée ou supprimée ; une contradiction non résolue est signalée.

Claude : l’import de l’index dans CLAUDE.md configure son chargement au démarrage
si les instructions projet sont activées. Codex : AGENTS.md prescrit sa lecture.
La transmission aux sous-agents est une responsabilité du conducteur, pas une
garantie d’injection de tous les runtimes. Ce lot ne teste pas cette injection
sur chaque runtime. Voir https://code.claude.com/docs/en/memory pour les imports.
Le concept de guide appartient à l’expérience Cursor citée ci-dessus ; les
budgets, chemins et contrôles présents sont notre adaptation portable.
