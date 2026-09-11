# Intégration locale — recette_agent

Préserver I1–I6, la médiation Control Plane et les exigences de replay/recette runtime. Le noyau outille les workflows de développement, pas le moteur de gouvernance du produit. Les seuils locaux plus stricts des recettes restent des gates obligatoires distinctes du score global. Stocker les rapports et preuves sous docs/tracking/ ; ne pas committer ces traces. Aucun KS n’est présent dans la base suivie : intégrer APEX et PDCA sans imposer un nouveau pipeline.

Source : noyau Wattson tools/agent-workflows, protocole méthode 2. Aucun moteur
supplémentaire. Les skills/commandes .claude lisent ce contrat directement.
Tests du noyau : `python3 -m unittest discover -s tools/agent-workflows/tests -v`.
Les fixtures sont synthétiques et ne prouvent pas l'état de l'application.
L'intégration ne change pas le runtime, les données, les installateurs ou l'UI.
Comparer les versions du noyau avant portage ; conserver les profils métier.
