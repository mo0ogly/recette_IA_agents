# Runbook -- overlay passerelle LLM (LiteLLM)

L'overlay wire (mitmproxy) capture le trafic de l'agent vers les **systemes cibles**
(ses "mains"). Ce runbook couvre l'overlay complementaire pour le **cerveau** de
l'agent : une passerelle **LiteLLM** OPTIONNELLE qui centralise et observe les
appels des agents vers les fournisseurs LLM (Groq, OpenAI, Anthropic, ...).

Elle est **desactivee par defaut** et constitue une SURCHARGE, jamais un
remplacement : la recette deterministe utilise `StubLlm`/`ReplayLlm` et n'appelle
jamais un modele reel (I4). La passerelle n'a d'interet que pour les runs en mode
reel.

## Ce que c'est

[LiteLLM](https://github.com/BerriAI/litellm) Proxy est une passerelle compatible
OpenAI : les clients parlent le format wire OpenAI, LiteLLM redistribue vers les
vrais fournisseurs et centralise l'auth, l'usage et le logging. inspect_ia_agents possede deja
un provider `openai_compat` (`base_url` configurable, wire OpenAI), donc connecter
un agent a la passerelle ne necessite **aucun changement de code** -- seulement un
backend qui pointe vers elle.

## Architecture

```
agent (Lane B) --OpenAI wire--> [LiteLLM container :4000] --> Groq / OpenAI / Anthropic ...
                                      (centralize, observe, log model calls)
```

- Service Docker `llm-proxy` (profil compose `llm`, image LiteLLM).
- `config/litellm.config.yaml` -- la `model_list` (une entree par route fournisseur) ;
  les cles se resolvent via `os.environ/<KEY>` (R8, jamais en dur). Le conteneur recoit
  les cles depuis le `.env` de l'operateur (la source de verite des secrets) via le
  passthrough compose `environment`.

## Demarrage (R19, jamais hand-launch)

```
./recette.sh llm-proxy up
```

`down|status|logs` gerent le conteneur. Le proxy ecoute sur `127.0.0.1:4000`
(override `INSPECT_IA_AGENTS_LLM_PROXY_PORT`).

## Utilisation depuis un agent

Configurer un `ai_backend` (onglet **Agents** de la console -> AI backends, ou l'API) :

| Champ | Valeur |
|-------|-------|
| `provider` | `openai_compat` |
| `base_url` | `http://127.0.0.1:4000` |
| `model` | une des entrees `model_name` (`groq-llama`, `openai-gpt`, `anthropic-claude`) |
| cle api (secret) | la `LITELLM_MASTER_KEY` (par defaut `sk-recette-local`) |

Ensuite, relier un agent a ce backend et le lancer en mode reel (IA) : chaque
appel modele passe desormais par la passerelle, ou LiteLLM le logue et le
centralise.

## Ajouter un fournisseur / modele

Editer `config/litellm.config.yaml` -- ajouter une entree `model_list` avec son
`model_name`, le `model` LiteLLM (`<vendor>/<model>`) et `api_key:
os.environ/<KEY>`. Transmettre la cle dans le bloc `environment` du `llm-proxy`
compose, et mettre la valeur dans `.env`. Redemarrer : `./recette.sh llm-proxy down && up`.

## Determinisme (I4)

La passerelle n'est jamais sur le chemin recette/replay : le replay utilise
`StubLlm`/`ReplayLlm`. La passerelle ne sert que pour les runs en mode reel, ou le
run est enregistre, pas rejoue.

## Preuve live

`scripts/smoke_llm_proxy.py` -- s'auto-skip sans Docker ; sinon il demarre la
passerelle et asserte que `GET /v1/models` liste les modeles configures (aucun
appel modele upstream, aucune cle fournisseur necessaire).

## Voir aussi

- `proxy-debug-console.md` -- l'overlay wire (mitmproxy), le pendant cote trafic
  cible de cette passerelle de trafic LLM.
- `real-slack-proxy.md` -- un proxy cible real_saas.
- `.claude/rules/secrets-source-of-truth.md` (R18) -- ou vivent les cles fournisseurs.
