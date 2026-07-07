# Runbook -- AI Copilot (dock, AI buttons, AI Prompts)

The AI Copilot is the console's operator assistant: a collapsible dock on the
left of every page (multi-turn conversation + help journal), contextual `IA`
help buttons spread across the pages, and an `AI Prompts` page to customize
the system prompts. It rides on the existing AI backends (`/ai-backends`):
no dedicated provider.

## Architecture

- **Backend**: `/assist` router (`recette/api/routers/assist.py`).
  - `GET/PUT/DELETE /assist/prompts[/{id}]`: the prompt catalog. Defaults
    live in code (`recette/api/assist_prompts.py`); only operator overrides
    are persisted (`data/assist_prompt_overrides.json`, gitignored) and
    hot-reloaded on every call.
  - `POST /assist/chat`: one conversation exchange through an `ai_backend`
    chosen by the console. The key is resolved server-side (R8), never
    transmitted nor returned.
  - `POST /assist/help`: contextual help. The client sends only a topic key
    (+ declared ids); grounding data is resolved server-side
    (`recette/api/assist_grounding.py`) through field allowlists, truncated,
    and fenced by anti prompt-injection delimiters.
  - `GET/DELETE /assist/sessions/{id}`: one session's consolidated memory
    (thread + journal), bounded (20 turns / 100 insights / 50 LRU sessions),
    in-memory (lost on API restart, by design).
  - `GET /assist/topics`: the grounding topic catalog.
- **Frontend**: `console/src/components/assist/` (Provider, Dock, buttons)
  and `console/src/pages/ia-prompts/`.

## Diagnostic path, not a decision path

The copilot is operator assistance: it NEVER enters the decision/replay path
(I4 does not apply, same documented stance as
`POST /config/ai-backends/{id}/test`). No event is appended to the audit
store. Fail-safe failure mode: any LLM error (missing key, unreachable
provider) returns HTTP 200 with `source: "error"` -- never a 500, never an
auto-retry.

## Security

- Secrets: a backend key never appears in an `/assist` response nor in a
  prompt; the `ai_backends.list` grounding only exposes the
  `key_configured` boolean (R8).
- Prompt injection: all untrusted content (journal recap, platform data) is
  fenced `<<<tag>>> ... <<<fin_tag>>>`; the system prompts declare fenced
  content is data, not instructions. Grounding fields go through an explicit
  allowlist (agent `system_prompt` and ground-truth values never leave).
- Client params not declared by a topic are silently dropped (never echoed
  into the prompt).

## Usage

1. Configure at least one AI backend (`/ai-backends`) with its key.
2. The dock (left rail): pick the backend, ask a question in the
   Conversation tab. The Journal tab consolidates the AI buttons' answers;
   `Effacer la session` forgets the memory.
3. The `IA` buttons (next to `? Aide` on pages) send the page context to the
   copilot; the answer lands in the Journal and feeds later exchanges.
4. The `AI Prompts` page (Agents menu): edit a prompt (Monaco),
   `Reinitialiser` to reset to default, `Localiser dans l'UI` to flash the
   matching trigger.

## Tests

```bash
docker compose run --rm tests python -m unittest tests.test_api_assist_routes tests.test_prompt_store
cd console && npx vitest run src/components/assist src/pages/ia-prompts
```
