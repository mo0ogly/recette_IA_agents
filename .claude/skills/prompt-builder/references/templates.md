# Prompt Templates par Categorie

Squelettes de base par type de prompt. Adapter selon la plateforme cible (voir platforms.md).

---

## SYSTEM - Role, comportement, contraintes

Pour : chatbots, assistants, agents, custom GPTs, system prompts Claude

```
Tu es {ROLE} specialise en {DOMAINE}.

## Contexte
{Description du domaine, de l'entreprise, du produit}

## Mission
{Objectif principal en 1-2 phrases}

## Regles
1. {Regle critique 1}
2. {Regle critique 2}
3. {Regle critique 3}

## Format de reponse
{Structure attendue : bullets, JSON, markdown, etc.}

## Limites
- Ne jamais {action interdite 1}
- Ne jamais {action interdite 2}
- Si incertain : {comportement de fallback}

## Exemples
Entree : {exemple input}
Sortie : {exemple output attendu}
```

**Criteres de qualite :**
- Role specifique (pas "expert en tout")
- Regles actionnables (pas "sois pertinent")
- Au moins 1 exemple input/output
- Comportement de fallback defini

---

## CREATIVE - Images, video, musique, texte creatif

Pour : Midjourney, DALL-E, Stable Diffusion, Suno, Udio, Claude/GPT en mode creatif

### Image (Midjourney / DALL-E / SD)

```
{sujet principal}, {action/pose}, {details visuels cles},
{medium/style : photographie, peinture, 3D, illustration},
{eclairage : golden hour, studio, neon, naturel},
{composition : close-up, wide angle, aerial, portrait},
{ambiance : cinematique, minimaliste, dramatique, paisible},
{qualite : highly detailed, 8k, photorealistic, masterpiece}
```

### Texte creatif (Claude / GPT)

```
Ecris {type : nouvelle, poeme, dialogue, scenario} sur le theme de {theme}.

## Ton
{formel, humoristique, poetique, sombre, leger}

## Contraintes
- Longueur : {X mots/paragraphes}
- Point de vue : {1ere/3eme personne, narrateur omniscient}
- Epoque/lieu : {contexte spatio-temporel}

## A eviter
- {cliche 1}
- {cliche 2}

## Inspiration (optionnel)
Style proche de {auteur/oeuvre}
```

---

## CODE - Generation, debug, refactor, review

Pour : Claude, GPT, Cursor, Windsurf, Bolt, Copilot

### Generation

```
## Contexte technique
- Langage : {langage + version}
- Framework : {framework + version}
- Dependances existantes : {liste}

## Tache
{Description precise de ce qu'il faut coder}

## Specifications
- Input : {type et format des entrees}
- Output : {type et format des sorties}
- Gestion erreurs : {comportement attendu}

## Contraintes
- {Convention de nommage}
- {Patterns a respecter}
- {Dependances autorisees/interdites}

## Tests attendus
- Cas nominal : {description}
- Cas limite : {description}
- Cas erreur : {description}
```

### Review / Debug

```
## Code a analyser
{coller le code}

## Probleme observe
{description du bug / comportement inattendu}

## Comportement attendu
{ce qui devrait se passer}

## Environnement
- {OS, runtime, version}
- {Logs d'erreur pertinents}

## Demande
{review securite, performance, lisibilite, debug, refactor}
```

---

## ANALYSIS - Data, recherche, extraction, resume

Pour : Claude, GPT, Perplexity, Gemini

### Analyse de donnees

```
## Donnees
{coller les donnees ou decrire la source}

## Question
{question precise a laquelle repondre}

## Format de reponse attendu
- {Tableau, graphique textuel, bullets, JSON}
- Inclure : {metriques, tendances, anomalies, recommandations}

## Contraintes
- Sources a citer : {oui/non, format}
- Niveau de confiance : indiquer si incertain
- Langue : {langue de sortie}
```

### Resume / Extraction

```
## Document source
{coller ou decrire le document}

## Objectif
{resumer, extraire les points cles, comparer, synthetiser}

## Public cible
{expert technique, manager, debutant}

## Format
- Longueur max : {X mots/bullets}
- Structure : {executive summary, bullets, tableau comparatif}
- Inclure : {citations, sources, recommandations}
```

---

## CONVERSATIONAL - Chatbot, assistant, agent

Pour : custom GPTs, Claude Projects, agents LangChain/CrewAI

```
## Identite
Nom : {nom du bot}
Role : {description en 1 phrase}
Personnalite : {traits de caractere, ton}

## Domaine de competence
{liste des sujets maitrises}

## Flux conversationnel
1. Accueil : {message d'introduction}
2. Qualification : {questions a poser pour comprendre le besoin}
3. Reponse : {structure de la reponse type}
4. Suivi : {propositions de suivi, relances}

## Garde-fous
- Hors scope : {sujets a refuser poliment}
- Escalade : {quand rediriger vers un humain}
- Confidentialite : {donnees a ne jamais stocker/repeter}

## Exemples de dialogue
User: {exemple question}
Bot: {exemple reponse}
User: {exemple follow-up}
Bot: {exemple reponse follow-up}
```
