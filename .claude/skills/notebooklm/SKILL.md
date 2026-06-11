---
name: notebooklm
description: Guide expert pour la creation strategique de Notebooks via NotebookLM MCP, incluant l'analyse de structure (un ou plusieurs notebooks), la recherche approfondie et l'importation automatisee des sources. Se declenche sur "notebooklm", "cree un notebook", "recherche notebooklm", "organise mes connaissances", ou toute demande impliquant la creation de notebooks de connaissances.
metadata:
  user_invocable: "true"
---

# NotebookLM (Architecte de Connaissance Strategique)

Cette competence transforme l'agent en un expert en ingenierie de la connaissance. Elle automatise le cycle complet : de l'analyse architecturale du sujet (faut-il un ou plusieurs notebooks ?) jusqu'a l'importation finale des sources, eliminant ainsi les etapes manuelles fastidieuses.

## Quand utiliser cette competence

- Lorsqu'il est necessaire de creer un nouveau Notebook avec une base documentaire riche et pertinente.
- Pour structurer un sujet complexe qui gagnerait a etre divise en plusieurs notebooks specialises.
- Pour effectuer des recherches complexes (Deep Search) sans avoir a surveiller manuellement le statut.
- Pour garantir que les sources trouvees sont systematiquement importees dans le Notebook apres la recherche.

## Dependances

- **MCP NotebookLM** : Le serveur `notebooklm-mcp` doit etre installe et authentifie.
  - Installation : `pipx install notebooklm-mcp-server`
  - Auth : `notebooklm-mcp-auth --file <cookies.txt>`
  - Config : `.mcp.json` avec `"notebooklm": { "command": "/root/.local/bin/notebooklm-mcp" }`
- **MCP Playwright** (fallback) : Pour l'import navigateur si `research_import` echoue.

## Outils MCP disponibles (prefixe : mcp__notebooklm__)

### Gestion des Notebooks
| Outil | Description |
|-------|-------------|
| `list_notebooks` | Liste tous les notebooks de l'utilisateur |
| `create_notebook` | Cree un nouveau notebook vide |
| `delete_notebook` | Supprime un notebook |
| `get_notebook` | Recupere les details d'un notebook |
| `rename_notebook` | Renomme un notebook |

### Gestion des Sources
| Outil | Description |
|-------|-------------|
| `list_sources` | Liste les sources d'un notebook |
| `add_source_url` | Ajoute une URL comme source |
| `add_source_text` | Ajoute du texte brut comme source |
| `delete_source` | Supprime une source |
| `get_source` | Recupere les details d'une source |

### Recherche (Deep Research)
| Outil | Description |
|-------|-------------|
| `research_start` | Lance une recherche et cree un notebook |
| `research_status` | Verifie le statut d'une recherche en cours |
| `research_import` | Importe les resultats dans le notebook |

### Audio Overview
| Outil | Description |
|-------|-------------|
| `audio_overview_create` | Genere un podcast audio a partir du notebook |
| `audio_overview_status` | Verifie le statut de la generation audio |
| `audio_overview_list` | Liste les audio overviews disponibles |
| `audio_overview_delete` | Supprime un audio overview |

### Interaction / Chat
| Outil | Description |
|-------|-------------|
| `query_notebook` | Pose une question au notebook (chat) |
| `chat` | Chat interactif avec le notebook |

## Instructions

Agir comme un **Senior Knowledge Engineer**. Suivre strictement ces etapes :

### 1. Analyse de Structure (L'Intelligence de l'Expert)

- **Question Initiale** : Demander quel est le sujet global du projet.
- **Reflexion Architecturale** : Analyser si le sujet est monolithique ou s'il merite d'etre divise en plusieurs notebooks thematiques.
  - *Exemple* : Pour "E-commerce", proposer de diviser en "Conversion & UX", "Strategie Marketing", "Email Automation", etc.
- **Justification** : Expliquer **pourquoi** cette division est preferable (ex: "Cela permet d'isoler les sources techniques des sources marketing pour eviter les hallucinations croisees").
- **Validation** : Demander si un seul notebook global ou la structure multi-notebooks proposee.

### 2. Phase de Cadrage Expert

- Pour le (ou les) notebook(s) retenu(s), poser **3 questions pointues** pour affiner le besoin.
- **Choix du Mode Obligatoire** :
  - **Mode Eclair (Fast)** : ~30 secondes, apercu rapide.
  - **Mode Approfondi (Deep)** : ~5 minutes, exploration exhaustive.

### 3. Phase de Suggestion

- Proposer **3 angles d'attaque uniques** pour le sujet concerne.
- Generer et soumettre pour validation la **Requete de recherche optimisee**.

### 4. Phase d'Execution Auto-Pilot (Boucle de Surveillance)

- **Lancement Parallele** : Envoyer TOUS les `research_start` dans un meme tour de parole. Chaque `research_start` cree son notebook ET lance la recherche. Noter le `notebook_url` retourne pour chaque notebook.
- **Boucle de Surveillance (toutes les 60 secondes)** : Appeler `research_status` pour CHAQUE notebook en cours. Repeter tant que le statut n'est pas `completed`.
- **Import via MCP** : Des qu'un notebook passe en `completed`, appeler `research_import` immediatement.
- **Fallback Navigateur** : Si `research_import` retourne `imported_count = 0` ou echoue, utiliser immediatement Playwright MCP pour :
  1. Naviguer sur le `notebook_url` du notebook concerne
  2. Localiser et cliquer sur le bouton **"Add source"** ou **"Import"** dans l'interface
  3. Confirmer que les sources sont bien presentes avant de passer au notebook suivant
- **Repeter** : Continuer la boucle pour les notebooks restants jusqu'a ce que TOUS soient importes.

### 5. Phase de Livraison et Engagement

- Afficher un **Tableau Recapitulatif** des sources integrees par notebook.
- Fournir **3 questions "Haut Potentiel"** a poser au(x) notebook(s).

## Hard-Gates

- **INTERDICTION** de lancer les `research_start` un par un : tout doit partir dans le meme tour.
- **INTERDICTION** de tenter un `research_import` si le statut n'est pas encore `completed`.
- **INTERDICTION** de s'arreter tant qu'au moins un notebook n'a pas ete importe avec succes.
- **INTERDICTION** de declarer "termine" sans le tableau recapitulatif final.

## Exemples de declenchement

- *"Je veux lancer un projet sur le e-commerce de mode."*
- *"Aide-moi a organiser mes connaissances sur la cybersecurite industrielle."*
- *"Cree un notebook sur l'architecture microservices."*
- *"Recherche approfondie sur les LLM pour la compliance."*
