---
name: creation-llm
description: >-
  Add a new LLM provider/backend to inspect_ia_agents so it appears on /ai-backends and
  is callable by Lane B agents. Use this WHENEVER the user wants to add, wire,
  port, or enable an AI provider/model vendor (OpenAI-compatible, Anthropic-wire,
  Bedrock/Converse, a coding-plan gateway, an OAuth/bearer endpoint, etc) -- e.g.
  "ajoute le provider X", "branche Mistral/Groq/Kimi/Qwen/Bedrock", "porte ce
  vendor hermes", "rends cette IA dispo dans /ai-backends", "ajoute un backend
  LLM". Reach for it even when the user just names a vendor and a key without
  saying "provider". It enforces VERBATIM source values (never invented
  base_url/env), the right wire base class, the exact touchpoints, and the gates.
---

# Adding an LLM provider to inspect_ia_agents

A provider is a class in `recette/llm.py` that turns an agent's `(system, history,
tools)` into an `LlmDecision` over one vendor's HTTP wire. Once registered, it is
selectable on `/ai-backends` and usable by Lane B. The console dropdown is
**backend-driven** (served by `GET /config/ai-providers`), so there is **no
frontend edit** -- adding the provider server-side surfaces it in the UX.

## Non-negotiables

- **R13 -- verbatim, never invent.** `BASE_URL` and the key env-var come from the
  authoritative source: the vendor's official docs, or a provider profile you can
  read (e.g. a `plugins/model-providers/<slug>/__init__.py` ProviderProfile). If
  you cannot verify the exact host/path/env, fetch it before coding. A guessed
  base_url that 404s is the failure mode this rule exists to prevent.
- **R14 -- wired is not verified.** Unit/contract tests with a stub client prove
  the shape, not that the vendor accepts the call. Never say it "works" live
  without a real key + a real call. Say "wired + tested, live unverified" and
  hand the operator the step (paste a key on `/ai-backends`, run the probe).
- **R8 -- keys are write-only.** The key is read from `api_key` arg then the env
  var; never logged, never returned. The per-backend key lives in the secret
  store; the env var is the fallback.
- **Determinism (I4).** Provider construction and `decide()` stay pure of clock /
  random. Retry/backoff, if any, belongs in the HTTP transport, not the decision.

## Step 1 -- Verify the wire (before writing code)

Establish, from the source: the **base_url** (with or without a version segment),
the **request path**, the **wire format**, the **auth header**, and the **env-var
name**. Pick the base class from the wire:

| Wire | Base class | What you set |
|------|-----------|--------------|
| OpenAI, bare host (path appends `/v1/chat/completions`) | `_OpenAiWireVendor` | `BASE_URL` (host), `ENV_KEY` |
| OpenAI, base_url already carries the version (path is just `/chat/completions`) | `_VersionedWireVendor` | `BASE_URL` (with version), `ENV_KEY` |
| Anthropic Messages (`/v1/messages`), `x-api-key` | subclass `AnthropicLlm` | `BASE_URL`, `ENV_KEY` |
| Anthropic-compatible but **bearer** auth (e.g. MiniMax) | subclass `AnthropicLlm`, override `_auth_headers` | `BASE_URL`, `ENV_KEY`, `_auth_headers` |
| Gemini `generateContent` | model on `GeminiLlm` | (one host, key var) |
| A genuinely new wire (Bedrock Converse, OpenAI Responses) | new class + `_to_*` / `_parse_*` helpers (see `BedrockLlm`) | full adapter + tests |

How to tell OpenAI bare-host from versioned-base: look at where the vendor serves
chat completions. `api.groq.com/openai` + `/v1/chat/completions` -> bare host
(`_OpenAiWireVendor`). `api.moonshot.ai/v1` + `/chat/completions` -> versioned
base (`_VersionedWireVendor`). Getting this wrong doubles or drops the `/v1`.

If the vendor uses OAuth or a token flow, do not build the flow: the operator
pastes the bearer/access token into the per-backend key field (it is stored in
the secret store like any key). Document that in the key hint and move on. AWS
SigV4 is the exception -- Bedrock takes a bearer API key
(`AWS_BEARER_TOKEN_BEDROCK`) so no SDK is needed.

## Step 2 -- Touchpoints (backend only)

For a standard OpenAI/Anthropic-wire vendor, three files:

1. **`recette/llm.py`**
   - The vendor class (4-8 lines for a wire subclass; a full adapter for a new wire).
   - A branch in `build_llm(...)`.
   - The provider id in the `_PROVIDERS` tuple (this tuple is the single source
     of truth -- the CLI choices and the console catalog both derive from it).
2. **`recette/api/routers/config.py`**
   - An entry in `_PROVIDER_ENV_KEY` (`provider_id -> ENV_VAR`). Skip only if the
     key is optional (like `openai_compat`).
   - If the provider takes a base_url, an entry in `_PROVIDER_BASE_URL`
     (`"required"` like openai_compat, or `"optional"` like a Bedrock region).
3. **`tests/test_llm.py`**
   - For a wire subclass: add the `(Class, BASE_URL, ENV_KEY)` row to the vendor
     table and a `build_llm(...)` assertion. For a new wire: a dedicated test
     class (auth header, request path, parse a tool call + a final answer).

**Do not touch the console** for the provider list -- `GET /config/ai-providers`
serves it from `_PROVIDERS` + `_PROVIDER_ENV_KEY`, and `AiBackendsPanel` fetches
it. Only touch the console if the provider needs a brand-new *form field* the
catalog can't express.

## Step 3 -- Gates (all must pass before "done")

```
ruff check recette/llm.py recette/api/routers/config.py tests/test_llm.py
python3 -m unittest tests.test_llm tests.test_cli tests.test_api_config_routes
cd console && npx vitest run src/pages/agents/AiBackendsPanel.test.tsx && npm run build
```

`AiBackendsPanel.test.tsx` already asserts the dropdown lists every catalog id, so
a new provider is covered once the backend test for `/config/ai-providers` passes.
Keep line length <= 100 (ruff E501): wrap long table rows.

## Step 4 -- Report honestly

State the provider id, base_url, env var, and wire. Then the live status per R14:
"wired + unit/contract tested, NOT live-verified (no key, no real call)". Tell the
operator to paste a key on `/ai-backends` and run the probe.

## Worked example -- a versioned-base OpenAI vendor

Source says: chat completions at `https://api.moonshot.ai/v1/chat/completions`,
key `KIMI_API_KEY`. Versioned base -> `_VersionedWireVendor`.

```python
class MoonshotLlm(_VersionedWireVendor):
    """Moonshot / Kimi -- OpenAI wire at api.moonshot.ai/v1. Key: KIMI_API_KEY."""

    BASE_URL = "https://api.moonshot.ai/v1"
    ENV_KEY = "KIMI_API_KEY"
```

Then: `build_llm` branch, `"moonshot"` in `_PROVIDERS`, `"moonshot":
"KIMI_API_KEY"` in `_PROVIDER_ENV_KEY`, a vendor-table row + factory assertion in
`tests/test_llm.py`. Run the gates. The provider now appears on `/ai-backends`
with no frontend change.

## Field gotchas (from wiring the existing ~22 providers)

These are the traps that actually cost time. Check them by reflex.

- **A vendor profile's `plugin.yaml` is metadata only.** When porting from a
  provider plugin (e.g. hermes-style `plugins/model-providers/<slug>/`), the real
  `base_url` / `env_vars` / `api_mode` live in the `__init__.py` ProviderProfile,
  not the `.yaml`. Read the `__init__.py`.
- **An `/anthropic` path means Anthropic wire, not OpenAI.** A base_url like
  `api.minimax.io/anthropic` is the Messages API even though the vendor also has
  an OpenAI mode elsewhere. Match the wire to the actual endpoint you target.
- **The env-var name is part of the source, not your invention.** Vendors often
  use a non-obvious var: Moonshot is `KIMI_API_KEY` (not `MOONSHOT_API_KEY`),
  Z.AI is `GLM_API_KEY`, Arcee is `ARCEEAI_API_KEY`, Hugging Face is `HF_TOKEN`.
  Copy the primary entry of the vendor's `env_vars` verbatim.
- **`_PROVIDERS` is the ONE source of truth -- don't hand-copy it.** The CLI
  choices (`recette/__main__.py` imports `_PROVIDERS as _LLM_PROVIDERS`), the
  CLI test (`tests/test_cli.py` imports `_PROVIDERS`), and the console catalog
  (`/config/ai-providers`) all derive from it. Add the id once, in the tuple.
- **Provider ids are snake_case** (`ollama_cloud`, `alibaba_coding_plan`), even
  when the vendor slug is kebab. Keep `_PROVIDERS`, `_PROVIDER_ENV_KEY`, the
  factory branch, and the env var consistent.
- **The test stub client exposes `last_path`, `last_body`, `headers`,
  `base_url`.** Use them to assert the exact request path (catches `/v1`
  doubling) and the auth header style (catches x-api-key vs bearer).
- **Verify-before-code pays off.** On the first pass of this corpus, guessing
  values produced ~8 wrong base_urls/env-vars (e.g. `api.z.ai/api/openai` vs the
  real `api.z.ai/api/paas/v4`). Reading the source first would have avoided every
  one. Fetch, then write.

## Anti-patterns

| Don't | Do |
|-------|----|
| Invent a base_url/env from memory | Fetch the vendor profile / official docs (R13) |
| Put `/v1` in both BASE_URL and the path | Match the base class to where the version lives |
| Hand-edit the console provider list | Let the dynamic catalog serve it |
| Build an OAuth device-code flow | Operator pastes the token into the key field |
| Claim it works after green tests | "Wired + tested, live unverified" + operator step (R14) |
| Anthropic-wire vendor with `x-api-key` when it wants bearer | Override `_auth_headers` (see `MinimaxLlm`) |
