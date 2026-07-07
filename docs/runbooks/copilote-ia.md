# Runbook -- Copilote IA (dock, boutons IA, Prompts IA)

Le Copilote IA est l'assistant operateur de la console : un dock repliable a
gauche de chaque page (conversation multi-tours + journal des aides), des
boutons `IA` d'aide contextuelle disperses dans les pages, et une page
`Prompts IA` pour personnaliser les prompts systeme. Il s'appuie sur les
backends IA existants (`/ai-backends`) : aucun provider dedie.

## Architecture

- **Backend** : routeur `/assist` (`recette/api/routers/assist.py`).
  - `GET/PUT/DELETE /assist/prompts[/{id}]` : catalogue de prompts. Les
    defauts vivent en code (`recette/api/assist_prompts.py`) ; seules les
    personnalisations sont persistees (`data/assist_prompt_overrides.json`,
    gitignore) et rechargees a chaud a chaque appel.
  - `POST /assist/chat` : un echange de conversation via un `ai_backend`
    choisi par la console. La cle est resolue cote serveur (R8), jamais
    transmise ni renvoyee.
  - `POST /assist/help` : aide contextuelle. Le client n'envoie qu'une cle de
    topic (+ ids declares) ; les donnees de grounding sont resolues cote
    serveur (`recette/api/assist_grounding.py`) par allowlist de champs,
    tronquees, et encadrees par des delimiteurs anti prompt-injection.
  - `GET/DELETE /assist/sessions/{id}` : memoire consolidee d'une session
    (thread + journal), bornee (20 tours / 100 insights / 50 sessions LRU),
    en memoire (perdue au redemarrage de l'API, par conception).
  - `GET /assist/topics` : catalogue des topics de grounding.
- **Frontend** : `console/src/components/assist/` (Provider, Dock, boutons)
  et `console/src/pages/ia-prompts/`.

## Chemin diagnostique, pas chemin de decision

Le copilote est une aide operateur : il n'entre JAMAIS dans le chemin de
decision/replay (I4 ne s'applique pas, meme posture documentee que
`POST /config/ai-backends/{id}/test`). Aucun evenement n'est ajoute au store
d'audit. Mode de defaillance fail-safe : toute erreur LLM (cle absente,
provider injoignable) retourne HTTP 200 avec `source: "error"` -- jamais un
500, jamais d'auto-retry.

## Securite

- Secrets : la cle d'un backend n'apparait jamais dans une reponse `/assist`
  ni dans un prompt ; le grounding `ai_backends.list` n'expose que le booleen
  `key_configured` (R8).
- Prompt-injection : tout contenu non fiable (recap du journal, donnees de la
  plateforme) est encadre `<<<tag>>> ... <<<fin_tag>>>` ; les prompts systeme
  declarent que ce contenu est de la donnee, pas des instructions. Les champs
  du grounding passent par une allowlist explicite (les `system_prompt` et
  valeurs de ground-truth des agents ne sortent jamais).
- Les params client non declares par un topic sont silencieusement ignores
  (jamais recopies dans le prompt).

## Utilisation

1. Configurer au moins un backend IA (`/ai-backends`) avec sa cle.
2. Le dock (rail gauche) : choisir le backend, poser une question dans
   l'onglet Conversation. L'onglet Journal consolide les reponses des
   boutons IA ; `Effacer la session` oublie la memoire.
3. Les boutons `IA` (a cote de `? Aide` sur les pages) envoient le contexte
   de la page au copilote ; la reponse arrive dans le Journal et nourrit les
   echanges suivants.
4. La page `Prompts IA` (menu Agents) : modifier un prompt (Monaco),
   `Reinitialiser` pour revenir au defaut, `Localiser dans l'UI` pour faire
   clignoter le declencheur concerne.

## Tests

```bash
docker compose run --rm tests python -m unittest tests.test_api_assist_routes tests.test_prompt_store
cd console && npx vitest run src/components/assist src/pages/ia-prompts
```
