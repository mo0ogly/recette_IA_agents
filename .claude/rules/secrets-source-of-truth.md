# R18 Secrets Source of Truth -- where API keys live, stop asking

## Why this rule exists

Repeated incident: the operator was asked for the Groq API key over and over,
and even pasted it into the chat (which leaks it). The key already lives in the
repo's secret stores. There is NEVER a reason to ask the operator for a key that
is already on disk, and NEVER a reason to accept one pasted in chat.

## The two on-disk secret sources (both gitignored, R8)

1. **`.env`** at the repo root -- provider env-var keys, one `KEY=VALUE` per line:
   `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
   `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`,
   `TOGETHER_API_KEY`, `FIREWORKS_API_KEY`. Template: `.env.example`.
   Gitignored by `.gitignore` (`.env`, `.env.*`, `!.env.example`).

2. **`data/backend_secrets.json`** -- the per-`ai_backend` key container,
   `{backend_id: api_key}`, managed by `recette/api/secret_store.py`
   (`BackendSecretStore`). Gitignored (`.gitignore` line: `data/backend_secrets.json`).
   Path override: `INSPECT_IA_AGENTS_BACKEND_SECRETS_PATH`.

## Resolution order at LLM call time

The per-backend secret from `data/backend_secrets.json` first, then the
provider's env-var fallback from the process environment (which `.env` populates).
Implemented inside the provider classes in `recette/llm.py` and the secret store.

## How to make a key available to a process

- API server (`python -m recette.api`): auto-loads `.env` via
  `recette/api/_dotenv.py::load_dotenv()` at startup. Nothing to do.
- Scripts / live runners (`scripts/run_*_live_groq.py`, `python -m recette
  orchestrate run`): call `load_dotenv()` once at startup (see
  `scripts/run_orchestration_live_groq.py`) OR the operator exports the var.
  An already-set environment variable always wins over `.env` (explicit override).

## The rule (BLOCKING)

1. **Never ask the operator for a key that resolves from the two sources above.**
   First check `.env` / `data/backend_secrets.json` / `os.environ`. Only ask if
   ALL are genuinely empty -- and then ask them to put it in `.env`, not in chat.
2. **Never accept a secret pasted into the chat as the storage mechanism.** If a
   key is pasted, write it to `.env` (gitignored) and tell the operator the key
   is now exposed in the transcript and should be rotated.
3. **Never hardcode a key** in source, config, tests, or commits (R8/R15). Never
   echo or log a key in plaintext.
4. **New code that needs a provider key reads it from the environment** (after
   `load_dotenv()`), never from a literal or a prompt.

## Quick check

```
git check-ignore .env data/backend_secrets.json    # both must print (ignored)
python3 -c "from recette.api._dotenv import load_dotenv; load_dotenv(); import os; print('GROQ_API_KEY' in os.environ)"
```

## Related

- `.claude/rules/no-hardcoded-secrets.md` (R8/R15) -- never commit/hardcode a secret.
- `recette/api/secret_store.py` -- the per-backend container + its guarantees.
- `recette/api/_dotenv.py` -- the stdlib `.env` loader.
