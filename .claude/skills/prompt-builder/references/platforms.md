# Platform-Specific Prompt Patterns

Reference des structures et syntaxes validees par plateforme. Mise a jour : 2026-03.

## Claude (Anthropic)

**Structure optimale :**
```xml
<context>
{contexte du domaine, donnees, contraintes}
</context>

<instructions>
{instructions precises, etape par etape}
</instructions>

<output_format>
{format attendu : JSON, markdown, code, etc.}
</output_format>

<examples>
<example>
<input>{entree}</input>
<output>{sortie attendue}</output>
</example>
</examples>

<constraints>
{ce qu'il ne doit PAS faire, limites, garde-fous}
</constraints>
```

**Bonnes pratiques :**
- Balises XML pour structurer les sections (Claude les parse nativement)
- System prompt pour le role et les contraintes durables
- Few-shot examples dans des balises `<example>`
- Chain-of-thought : demander de "reflechir etape par etape" ou utiliser `<thinking>` tags
- Prefilling : commencer la reponse assistant pour guider le format
- Etre direct : pas de formules de politesse, aller droit au but
- Long context : mettre les donnees longues en DEBUT de prompt, instructions a la FIN

**Anti-patterns :**
- "Tu es un assistant utile" (deja le comportement par defaut)
- Instructions contradictoires entre system et user
- Prompts trop courts sans contexte (Claude sous-performe)

---

## GPT-4 / ChatGPT (OpenAI)

**Structure optimale :**
```
System: {role + contraintes + format}
User: {tache + contexte + exemples}
Assistant: {prefill optionnel}
```

**Bonnes pratiques :**
- System message pour le persona, les regles, le format de sortie
- Delimiter les sections avec `###` ou `---` ou `"""`
- Few-shot : alterner User/Assistant messages
- JSON mode : ajouter `"response_format": {"type": "json_object"}` dans l'API
- Chain-of-thought : "Let's think step by step"
- Temperature : 0-0.3 pour factuel, 0.7-1.0 pour creatif
- Structured outputs : utiliser function calling / tools pour formats stricts

**Anti-patterns :**
- System prompt trop long (>2000 tokens degrade la qualite)
- Melanger plusieurs taches dans un seul prompt
- "Don't hallucinate" (inefficace, preferer "If unsure, say 'I don't know'")

---

## Midjourney

**Structure optimale :**
```
{sujet principal}, {details visuels}, {style/medium}, {eclairage}, {composition} --ar {ratio} --v {version} --s {stylize} --q {quality}
```

**Parametres :**
- `--ar 16:9` / `--ar 1:1` / `--ar 9:16` : ratio d'aspect
- `--v 7` : version du modele (7 = derniere stable)
- `--s 0-1000` : stylisation (0=fidele, 1000=artistique)
- `--q .25 / .5 / 1` : qualite (1=max, .25=rapide)
- `--no {element}` : exclusion negative
- `--chaos 0-100` : variabilite des resultats
- `--w` : weird factor
- `::2` : poids sur un element (mot::poids)

**Bonnes pratiques :**
- Commencer par le sujet principal, pas le style
- Termes photographiques : "35mm", "bokeh", "golden hour", "macro"
- Artistes/styles : "in the style of", "inspired by"
- Qualite : "highly detailed", "8k", "photorealistic"
- Negatifs avec `--no` plutot que "without" dans le texte
- Ordre des mots = importance (debut = plus de poids)

---

## Stable Diffusion (SDXL / SD3 / Flux)

**Structure positive :**
```
{sujet}, {description detaillee}, {style}, {qualite}
```

**Structure negative :**
```
{defauts a eviter}
```

**Syntaxe poids :**
- `(mot:1.4)` : augmenter l'importance
- `(mot:0.6)` : reduire l'importance
- `[mot]` : reduire (syntaxe alternative)
- `(mot1:1.2), (mot2:0.8)` : ponderation relative

**Bonnes pratiques :**
- Negative prompt indispensable : "blurry, low quality, deformed, extra limbs, watermark"
- CFG Scale : 7-12 pour la plupart des cas
- Steps : 20-30 pour SDXL, 15-25 pour Flux
- Sampler : DPM++ 2M Karras (fiable), Euler a (rapide)
- Embeddings et LoRA : `<lora:nom:poids>` dans le prompt
- SDXL : prompts plus longs et descriptifs que SD 1.5

---

## Cursor / Windsurf / Bolt (AI Code Editors)

**Structure optimale :**
```
## Context
{description du projet, stack, fichiers concernes}

## Task
{tache precise avec criteres d'acceptation}

## Constraints
- {convention de nommage}
- {patterns existants a respecter}
- {dependencies autorisees}

## Examples
{input -> output attendu}
```

**Bonnes pratiques :**
- Mentionner les fichiers concernes explicitement (`@file.ts`)
- Decrire le pattern existant du projet (DRY : suivre ce qui existe)
- Contraintes techniques : version, framework, conventions
- Tests : specifier les cas de test attendus
- Scope : une tache par prompt, pas de mega-prompts

---

## Gemini (Google)

**Bonnes pratiques :**
- Grounding avec Google Search : activer pour les faits recents
- Structured output : JSON schema en parametre
- System instructions : role + contraintes (similaire a OpenAI)
- Multi-modal : decrire les images/videos fournies dans le prompt
- Safety settings : configurer les seuils par categorie
- Long context (1M+ tokens) : "needle in haystack" = instructions a la fin

---

## Perplexity

**Bonnes pratiques :**
- Focus modes : Academic, Writing, Math, Video, Social
- Demander les sources explicitement
- Questions precises > questions ouvertes
- Follow-up chains : construire sur les reponses precedentes
- Pro Search : questions complexes multi-etapes
- Specifier la profondeur voulue : "give me a comprehensive analysis" vs "quick answer"

---

## LLMs Locaux (Ollama, LM Studio, vLLM)

**Bonnes pratiques :**
- Prompts plus explicites (modeles plus petits = moins d'inference)
- System prompt court (<500 tokens pour 7B)
- Format de chat : respecter le template du modele (ChatML, Llama, etc.)
- Eviter les instructions complexes multi-etapes (decomposer)
- Temperature 0 pour les taches deterministes
- Repeter les contraintes critiques (les petits modeles oublient)
