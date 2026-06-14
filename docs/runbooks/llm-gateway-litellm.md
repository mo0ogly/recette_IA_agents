# Runbook -- LLM gateway overlay (LiteLLM)

The wire overlay (mitmproxy) captures the agent's traffic to **target systems**
(its "hands"). This runbook covers the complementary overlay for the agent's
**brain**: an OPTIONAL **LiteLLM** gateway that centralizes and observes the
agents' calls to LLM providers (Groq, OpenAI, Anthropic, ...).

It is **off by default** and a SURCHARGE, never a replacement: the deterministic
recette uses `StubLlm`/`ReplayLlm` and never calls a real model (I4). The
gateway only matters for real-mode runs.

## What it is

[LiteLLM](https://github.com/BerriAI/litellm) Proxy is an OpenAI-compatible
gateway: clients speak the OpenAI wire format, LiteLLM fans out to the real
vendors and centralizes auth, usage, and logging. inspect_ia_agents already has an
`openai_compat` provider (configurable `base_url`, OpenAI wire), so wiring an
agent to the gateway needs **no code change** -- only a backend pointing at it.

## Architecture

```
agent (Lane B) --OpenAI wire--> [LiteLLM container :4000] --> Groq / OpenAI / Anthropic ...
                                      (centralize, observe, log model calls)
```

- Docker service `llm-proxy` (compose profile `llm`, LiteLLM image).
- `config/litellm.config.yaml` -- the `model_list` (one entry per vendor route);
  keys resolve via `os.environ/<KEY>` (R8, never hardcoded). The container gets
  the keys from the operator's `.env` (the secret source of truth) through the
  compose `environment` passthrough.

## Bring it up (R19, never hand-launch)

```
./recette.sh llm-proxy up
```

`down|status|logs` manage the container. The proxy binds `127.0.0.1:4000`
(override `INSPECT_IA_AGENTS_LLM_PROXY_PORT`).

## Use it from an agent

Configure an `ai_backend` (console **Agents** tab -> AI backends, or the API):

| Field | Value |
|-------|-------|
| `provider` | `openai_compat` |
| `base_url` | `http://127.0.0.1:4000` |
| `model` | one of the `model_name` entries (`groq-llama`, `openai-gpt`, `anthropic-claude`) |
| api key (secret) | the `LITELLM_MASTER_KEY` (default `sk-recette-local`) |

Then bind an agent to that backend and run it in real (IA) mode: every model
call now goes through the gateway, where LiteLLM logs and centralizes it.

## Add a vendor / model

Edit `config/litellm.config.yaml` -- add a `model_list` entry with its
`model_name`, the LiteLLM `model` (`<vendor>/<model>`), and `api_key:
os.environ/<KEY>`. Forward the key in the compose `llm-proxy` `environment`
block, and put the value in `.env`. Restart: `./recette.sh llm-proxy down && up`.

## Determinism (I4)

The gateway is never on the recette/replay path: replay uses `StubLlm`/
`ReplayLlm`. The gateway is for real-mode runs only, where the run is recorded,
not replayed.

## Live proof

`scripts/smoke_llm_proxy.py` -- self-skips without Docker; otherwise brings the
gateway up and asserts `GET /v1/models` lists the configured models (no upstream
model call, no provider key needed).

## Related

- `proxy-debug-console.md` -- the wire overlay (mitmproxy), the target-traffic
  counterpart of this LLM-traffic gateway.
- `real-slack-proxy.md` -- a real_saas target proxy.
- `.claude/rules/secrets-source-of-truth.md` (R18) -- where the provider keys live.
