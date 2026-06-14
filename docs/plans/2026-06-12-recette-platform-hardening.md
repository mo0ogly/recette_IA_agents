# Recette Platform Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire every mocked area of the recette platform into a functional, observable system: 5 AI providers, a CRUD server registry with real local HTTP mock targets, a reusable log console in every window, and ground-truth verdict scoring.

**Architecture:** Approach A from `docs/plans/2026-06-12-recette-platform-hardening-design.md` -- keep `recette/platform/` (gateway, policy, eventstore, proxy), `recette/llm.py` and the React console; extend them. Config stays one versioned JSON file (`ConfigStore`). New entities: `servers` section, `ground_truth` on agents, verdict store.

**Tech Stack:** Python stdlib + FastAPI (optional extra), unittest, React 18 + TypeScript + Vitest, WebSocket (existing per-run stream) + incremental polling of `/audit/events` for log tails.

**Conventions (mandatory):** R12 code/comments in English. R8 keys via env only (`*_env` fields). I1 no event mutation. I4 no clock/random in decision paths (latency measurement in the diagnostic `test` endpoint is allowed: not a decision path). I5 all side effects through proxies. R16 every new console component gets a real-payload fixture + render-and-assert test. No emojis anywhere.

**Test commands:**
- Python: `python3 -m unittest discover -s tests -v` (or single: `python3 -m unittest tests.test_llm -v`)
- Console: `cd console && npx vitest run` (single file: `npx vitest run src/pages/agents/index.test.tsx`)

**Pre-existing dirty files:** `git status` shows uncommitted changes in `config/inspect_ia_agents.config.json`, `console/src/pages/agents/*`, `console/src/types/platform.ts`, `recette/{events,forge,tools}.py`. Before Task 1: run `git stash list && git diff --stat` to inspect; commit them on their own if they are coherent work-in-progress (`git add -p`), never mix them into plan commits.

---

## Workstream A -- AI providers (Gemini, Groq, OpenAI-compatible)

### Task A1: OpenAiCompatLlm (generic base_url, covers Ollama/proxies)

**Files:**
- Modify: `recette/llm.py` (after `OpenAiLlm`, before the provider factory)
- Test: `tests/test_llm.py`

**Step 1: Write the failing tests** (append to `tests/test_llm.py`, reuse the existing `_StubResponse`/stub-client pattern at the top of that file):

```python
class OpenAiCompatTests(unittest.TestCase):
    def test_tool_call_parsed_from_openai_wire_format(self) -> None:
        client = _StubClient(
            _StubResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "read_repo",
                                            "arguments": "{\"resource\": \"acme/x\"}",
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
        )
        llm = OpenAiCompatLlm(model="qwen2.5", base_url="http://localhost:11434/v1", client=client)
        decision = llm.decide(system="s", history=[Message(role="user", content="go")], tools=TOOLS)
        self.assertTrue(decision.is_tool_call)
        self.assertEqual(decision.tool_name, "read_repo")
        self.assertEqual(decision.tool_args, {"resource": "acme/x"})

    def test_no_api_key_required(self) -> None:
        # Local OpenAI-compatible servers (Ollama) have no key; must construct keyless.
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            llm = OpenAiCompatLlm(model="qwen2.5", base_url="http://localhost:11434/v1")
            self.assertIsNotNone(llm)
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old

    def test_base_url_v1_suffix_normalized(self) -> None:
        # ".../v1" and bare base must both end up posting to /v1/chat/completions
        client = _StubClient(_StubResponse({"choices": []}))
        llm = OpenAiCompatLlm(model="m", base_url="http://h:1/v1", client=client)
        llm.decide(system="s", history=[], tools=[])
        self.assertEqual(client.last_path, "/v1/chat/completions")
```

Check what the existing stub client in `tests/test_llm.py` is called (read the file first); if it does not record `last_path`, extend it to store the last `post(path=...)`.

**Step 2:** Run `python3 -m unittest tests.test_llm -v` -- expected FAIL: `ImportError: cannot import name 'OpenAiCompatLlm'`.

**Step 3: Implement** in `recette/llm.py`:

```python
class OpenAiCompatLlm(OpenAiLlm):
    """OpenAI-wire-compatible backend with a configurable base URL.

    Covers Groq, Ollama, vLLM, LiteLLM proxies. The API key is optional:
    local servers run keyless; remote ones read api_key_env at call site.
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        if client is None:
            # Normalize: callers may pass ".../v1"; paths below already start with /v1.
            base = base_url.rstrip("/")
            if base.endswith("/v1"):
                base = base[: -len("/v1")]
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            client = StdlibHttpClient(base, headers=headers)
        self._client = client
```

(`decide` is inherited unchanged from `OpenAiLlm`.)

**Step 4:** Run `python3 -m unittest tests.test_llm -v` -- expected PASS.

**Step 5: Commit**

```bash
git add recette/llm.py tests/test_llm.py
git commit -m "feat(llm): OpenAiCompatLlm with configurable base_url (Ollama, proxies)"
```

### Task A2: GroqLlm

Groq speaks the exact OpenAI wire format at `https://api.groq.com/openai/v1/chat/completions`, key in `GROQ_API_KEY`.

**Files:** Modify `recette/llm.py`; Test `tests/test_llm.py`.

**Step 1: Failing test:**

```python
class GroqTests(unittest.TestCase):
    def test_requires_key_when_no_client(self) -> None:
        old = os.environ.pop("GROQ_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                GroqLlm(model="llama-3.3-70b-versatile")
        finally:
            if old is not None:
                os.environ["GROQ_API_KEY"] = old

    def test_decide_uses_openai_wire_format(self) -> None:
        client = _StubClient(_StubResponse({"choices": [{"message": {"content": "ok"}}]}))
        llm = GroqLlm(model="llama-3.3-70b-versatile", client=client)
        decision = llm.decide(system="s", history=[], tools=[])
        self.assertEqual(decision.kind, "final")
        self.assertEqual(decision.text, "ok")
        self.assertEqual(client.last_path, "/v1/chat/completions")
```

**Step 2:** Run -- FAIL (no `GroqLlm`).

**Step 3: Implement:**

```python
class GroqLlm(OpenAiLlm):
    """Groq cloud backend -- OpenAI wire format at api.groq.com. Key: GROQ_API_KEY."""

    BASE_URL = "https://api.groq.com/openai"

    def __init__(
        self, *, model: str, client: _PostClient | None = None, api_key: str | None = None
    ) -> None:
        self._model = model
        if client is None:
            key = api_key or os.environ.get("GROQ_API_KEY")
            if not key:
                raise RuntimeError("GROQ_API_KEY not set (or pass client/api_key)")
            client = StdlibHttpClient(self.BASE_URL, headers={"Authorization": f"Bearer {key}"})
        self._client = client
```

**Step 4:** Run -- PASS. **Step 5:** Commit `feat(llm): GroqLlm backend (OpenAI wire format, GROQ_API_KEY)`.

### Task A3: GeminiLlm

Gemini wire format differs: `POST /v1beta/models/{model}:generateContent`, header `x-goog-api-key`, tools as `functionDeclarations`, response `candidates[0].content.parts[]` holding `{"functionCall": {...}}` or `{"text": ...}`.

**Files:** Modify `recette/llm.py`; Test `tests/test_llm.py`.

**Step 1: Failing tests:**

```python
class GeminiTests(unittest.TestCase):
    def test_function_call_parsed(self) -> None:
        client = _StubClient(
            _StubResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"functionCall": {"name": "read_repo", "args": {"resource": "acme/x"}}}
                                ]
                            }
                        }
                    ]
                }
            )
        )
        llm = GeminiLlm(model="gemini-2.0-flash", client=client)
        decision = llm.decide(system="s", history=[Message(role="user", content="go")], tools=TOOLS)
        self.assertTrue(decision.is_tool_call)
        self.assertEqual(decision.tool_name, "read_repo")
        self.assertEqual(decision.tool_args, {"resource": "acme/x"})
        self.assertEqual(client.last_path, "/v1beta/models/gemini-2.0-flash:generateContent")

    def test_text_answer_parsed(self) -> None:
        client = _StubClient(
            _StubResponse({"candidates": [{"content": {"parts": [{"text": "done"}]}}]})
        )
        llm = GeminiLlm(model="gemini-2.0-flash", client=client)
        decision = llm.decide(system="s", history=[], tools=[])
        self.assertEqual(decision.kind, "final")
        self.assertEqual(decision.text, "done")

    def test_requires_key_when_no_client(self) -> None:
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                GeminiLlm(model="gemini-2.0-flash")
        finally:
            if old is not None:
                os.environ["GEMINI_API_KEY"] = old
```

**Step 2:** Run -- FAIL.

**Step 3: Implement:**

```python
# --- Gemini ------------------------------------------------------------------------------


def _to_gemini_contents(history: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in history:
        if m.role == "assistant":
            out.append({"role": "model", "parts": [{"text": m.content}]})
        elif m.role == "tool":
            out.append(
                {
                    "role": "user",
                    "parts": [{"text": f"[tool {m.tool_name} result] {m.content}"}],
                }
            )
        else:
            out.append({"role": "user", "parts": [{"text": m.content}]})
    return out


def _parse_gemini(data: dict) -> LlmDecision:
    candidates = data.get("candidates") or []
    if not candidates:
        return LlmDecision(kind="final", text="", raw=data)
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        call = part.get("functionCall")
        if call:
            return LlmDecision(
                kind="tool_call",
                tool_name=call.get("name"),
                tool_args=call.get("args", {}) or {},
                text="".join(text_parts),
                raw=data,
            )
        if "text" in part:
            text_parts.append(part.get("text", ""))
    return LlmDecision(kind="final", text="".join(text_parts), raw=data)


class GeminiLlm:
    """Google Gemini backend (generateContent API). Key: GEMINI_API_KEY."""

    BASE_URL = "https://generativelanguage.googleapis.com"

    def __init__(
        self, *, model: str, client: _PostClient | None = None, api_key: str | None = None
    ) -> None:
        self._model = model
        if client is None:
            key = api_key or os.environ.get("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY not set (or pass client/api_key)")
            client = StdlibHttpClient(self.BASE_URL, headers={"x-goog-api-key": key})
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body: dict = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": _to_gemini_contents(history),
        }
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": t.parameters}
                        for t in tools
                    ]
                }
            ]
        resp = self._client.post(f"/v1beta/models/{self._model}:generateContent", json=body)
        resp.raise_for_status()
        return _parse_gemini(resp.json())
```

**Step 4:** Run -- PASS. **Step 5:** Commit `feat(llm): GeminiLlm backend (generateContent, GEMINI_API_KEY)`.

### Task A4: extend build_llm to 5 providers

**Files:** Modify `recette/llm.py` (factory at bottom); Test `tests/test_llm.py`.

**Step 1: Failing test:**

```python
class BuildLlmFactoryTests(unittest.TestCase):
    def test_all_five_providers_constructible_with_stub_client(self) -> None:
        client = _StubClient(_StubResponse({"choices": [], "candidates": [], "content": []}))
        for provider in ("anthropic", "openai", "gemini", "groq", "openai_compat"):
            llm = build_llm(
                provider, "some-model", client=client, base_url="http://localhost:11434/v1"
            )
            self.assertIsNotNone(llm)

    def test_unknown_provider_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_llm("mistral", "m")

    def test_openai_compat_requires_base_url(self) -> None:
        with self.assertRaises(ValueError):
            build_llm("openai_compat", "m")
```

**Step 2:** Run -- FAIL.

**Step 3: Implement** (replace the existing factory):

```python
_PROVIDERS = ("anthropic", "openai", "gemini", "groq", "openai_compat")


def build_llm(
    provider: str,
    model: str,
    *,
    client: _PostClient | None = None,
    base_url: str | None = None,
) -> LlmBackend:
    """Construct a live provider backend by name. Keys come from env (R8)."""
    if provider == "anthropic":
        return AnthropicLlm(model=model, client=client)
    if provider == "openai":
        return OpenAiLlm(model=model, client=client)
    if provider == "gemini":
        return GeminiLlm(model=model, client=client)
    if provider == "groq":
        return GroqLlm(model=model, client=client)
    if provider == "openai_compat":
        if not base_url:
            raise ValueError("openai_compat requires base_url")
        return OpenAiCompatLlm(model=model, base_url=base_url, client=client)
    raise ValueError(f"unknown provider {provider!r}; known: {', '.join(_PROVIDERS)}")
```

Then grep callers: `grep -rn "build_llm" recette/ tests/` -- update every call site that must now pass `base_url` from the backend config entry (look at `recette/lane_b.py` and `recette/api/runners.py`; thread the agent's `ai_backend` entry through, taking `base_url` from the backend dict when present).

**Step 4:** Run full suite `python3 -m unittest discover -s tests -v` -- PASS. **Step 5:** Commit `feat(llm): build_llm covers gemini, groq, openai_compat`.

### Task A5: backend connectivity test endpoint

**Files:**
- Modify: `recette/api/routers/config.py`
- Modify: `recette/api/app.py` (inject `app.state.llm_factory = build_llm` so tests can override)
- Test: `tests/test_api_config_routes.py`

**Step 1: Failing test** (follow the existing TestClient pattern in `tests/test_api_config_routes.py` -- read it first; reuse its app/client fixture):

```python
class AiBackendTestEndpointTests(unittest.TestCase):
    def test_test_endpoint_reports_ok_with_stub_factory(self) -> None:
        app, client = make_app_and_client(self)  # match existing helper name in this file
        client.post("/config/ai-backends", json={"id": "b1", "provider": "groq", "model": "m"})

        def fake_factory(provider, model, *, client=None, base_url=None):
            return StubLlm([LlmDecision(kind="final", text="pong")])

        app.state.llm_factory = fake_factory
        resp = client.post("/config/ai-backends/b1/test")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIn("latency_ms", body)

    def test_test_endpoint_reports_error_when_key_missing(self) -> None:
        app, client = make_app_and_client(self)
        client.post("/config/ai-backends", json={"id": "b2", "provider": "gemini", "model": "m"})
        os.environ.pop("GEMINI_API_KEY", None)
        resp = client.post("/config/ai-backends/b2/test")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("GEMINI_API_KEY", body["error"])

    def test_test_endpoint_404_for_unknown_backend(self) -> None:
        _, client = make_app_and_client(self)
        self.assertEqual(client.post("/config/ai-backends/nope/test").status_code, 404)
```

**Step 2:** Run `python3 -m unittest tests.test_api_config_routes -v` -- FAIL (405/404).

**Step 3: Implement** in `routers/config.py`:

```python
@router.post("/ai-backends/{backend_id}/test")
def test_ai_backend(request: Request, backend_id: str) -> dict:
    """Diagnostic connectivity probe: one minimal real call to the provider.

    Not a decision path (I4 does not apply): wall-clock latency is reported
    for the operator. Failure mode: any error -> ok=False with the message,
    never an exception leaking as HTTP 500.
    """
    backend = next(
        (b for b in _store(request).read()["ai_backends"] if b["id"] == backend_id), None
    )
    if backend is None:
        raise HTTPException(status_code=404, detail=f"no ai backend {backend_id!r}")
    factory = getattr(request.app.state, "llm_factory", None) or build_llm
    started = time.perf_counter()
    try:
        llm = factory(backend["provider"], backend["model"], base_url=backend.get("base_url"))
        decision = llm.decide(
            system="You are a connectivity probe. Reply with one word.",
            history=[Message(role="user", content="ping")],
            tools=[],
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": True, "latency_ms": latency_ms, "kind": decision.kind}
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "error": str(exc)}
```

Add imports (`time`, `HTTPException`, `from ...llm import Message, build_llm`). In `app.py` factory, set `app.state.llm_factory = build_llm`.

**Step 4:** Run -- PASS. **Step 5:** Commit `feat(api): POST /config/ai-backends/{id}/test connectivity probe`.

### Task A6: console -- AiBackendsPanel providers + Test button

**Files:**
- Modify: `console/src/pages/agents/AiBackendsPanel.tsx`
- Modify: `console/src/types/platform.ts` (AiBackend type: add `"gemini" | "groq" | "openai_compat"` to provider union, optional `base_url`)
- Modify: `console/src/api/client.ts` (add `testAiBackend(id): Promise<{ok: boolean; latency_ms: number; error?: string}>` -- unwrap envelope exactly like neighboring functions; read the file to match the envelope convention)
- Create: `console/src/pages/agents/__fixtures__/aiBackendTest.fixture.json`
- Test: extend the AiBackendsPanel coverage in `console/src/pages/agents/index.test.tsx` (or its own test file if the panel has one)

**Step 1: Capture the real fixture.** Start the API (`python3 -m recette.api`), create a backend, then:

```bash
curl -s -X POST http://localhost:8000/config/ai-backends/b1/test > console/src/pages/agents/__fixtures__/aiBackendTest.fixture.json
```

(No key in env -> the fixture is the real `ok:false` error shape. Good: that is the variant most likely to break the UI.)

**Step 2: Write the failing render-and-assert test:** render the panel with a mocked client whose `testAiBackend` resolves with the fixture, click the `Test` button on a row, assert the red status dot and the error text appear; second case with `{ok:true,latency_ms:42,kind:"final"}` asserts the green dot and `42 ms`.

**Step 3:** `cd console && npx vitest run src/pages/agents` -- FAIL.

**Step 4: Implement.** In the panel: provider `<select>` now lists `anthropic | openai | gemini | groq | openai_compat`; when `openai_compat` is selected show a required `base_url` text input; each backend row gets a `Test` button, a status dot (`untested` grey / `ok` green / `error` red) and the latency or error message. Match the existing styling of the panel (read it first).

**Step 5:** `npx vitest run` -- PASS, plus `npx tsc --noEmit` clean.

**Step 6:** Commit `feat(console): ai backend test button + gemini/groq/openai_compat providers`.

**Live verification (R14) before declaring workstream A done:** with at least one real key in env, run API + console, click Test on a real backend, observe green dot + latency. If no key available, state exactly: "livre, a verifier par toi" + steps.

---

## Workstream B -- Server registry (observable mock targets)

### Task B1: ConfigStore servers section

**Files:** Modify `recette/api/config_store.py`; Test `tests/test_api_config_store.py`.

**Step 1: Failing tests** (mirror the existing agent CRUD tests in that file):

```python
class ServerSectionTests(unittest.TestCase):
    def _store(self):  # match existing tmp-path helper in this file
        ...

    def test_add_list_update_delete_server(self) -> None:
        store = self._store()
        store.add_server({"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101})
        self.assertEqual(store.read()["servers"][0]["id"], "gh-mock")
        store.update_server("gh-mock", {"port": 9102})
        self.assertEqual(store.read()["servers"][0]["port"], 9102)
        store.delete_server("gh-mock")
        self.assertEqual(store.read()["servers"], [])

    def test_duplicate_server_id_rejected(self) -> None: ...
    def test_unknown_mode_rejected(self) -> None:
        # modes: mock_local | declared_url | real_saas
        ...
    def test_mock_local_requires_port_declared_url_requires_base_url(self) -> None: ...
    def test_read_defaults_servers_to_empty_list(self) -> None: ...
```

Fill the `...` bodies following the agent-test style already in the file.

**Step 2:** Run -- FAIL. **Step 3: Implement:** `_default()` gains `"servers": []`; `read()` gains `cfg.setdefault("servers", [])`; add `_SERVER_MODES = {"mock_local", "declared_url", "real_saas"}`, `_check_server(server)` validating id/system/mode and the mode-specific required field, then `list_servers / get_server / add_server / update_server / delete_server` symmetrical to the agent methods (raise `UnknownServerError(LookupError)` for missing ids). **Step 4:** PASS. **Step 5:** Commit `feat(config): servers section in ConfigStore (mock_local/declared_url/real_saas)`.

### Task B2: /config/servers CRUD router

**Files:** Modify `recette/api/routers/config.py`; Test `tests/test_api_config_routes.py`.

Same TDD rhythm: failing tests for `GET/POST/PUT/DELETE /config/servers` (201 on create, 409 on duplicate, 404 on unknown, 204 on delete) copied from the agent-route tests; implement by delegating to the store exactly as the agent routes do. Commit `feat(api): /config/servers CRUD`.

### Task B3: mock server health endpoint + access log

**Files:** Modify `recette/lab/mock_server.py`; Test `tests/test_lab_server_lifecycle.py` (create).

**Step 1: Failing test:** boot a `ThreadingHTTPServer` from `mock_server` on port 0 (ephemeral) in a thread, then assert:
- `GET /health` returns 200 `{"success": true, "data": {"status": "up", "systems": [...]}}`.
- After one `POST /github/execute` with `{"event_id": "e1", "action_type": "read_repo", "resource": "acme/x", "payload": {}}`, the access-log file (path injected via `INSPECT_IA_AGENTS_LAB_ACCESS_LOG`) contains one JSON line with `event_id`, `target_system`, `action_type`, `resource`, `status`.

**Step 2:** FAIL. **Step 3: Implement:**
- Add `do_GET` to `_Handler`: path `/health` -> 200 envelope with `sorted(_HANDLERS)`; anything else 404.
- In the POST path, after dispatch, append one JSON line (sort_keys) to the file named by `INSPECT_IA_AGENTS_LAB_ACCESS_LOG` when that env var is set (open in append mode per request; no timestamp -- the event_id already orders the trace, I4). No env var -> no file writes.

**Step 4:** PASS. **Step 5:** Commit `feat(lab): /health endpoint + JSONL access log for the mock server`.

### Task B4: ServerManager -- start/stop mock_local processes

**Files:**
- Create: `recette/api/server_manager.py`
- Modify: `recette/api/app.py` (instantiate `app.state.server_manager`, shut it down on app shutdown)
- Test: `tests/test_lab_server_lifecycle.py`

**Step 1: Failing tests:**

```python
class ServerManagerTests(unittest.TestCase):
    def test_start_creates_live_process_and_health_answers(self) -> None:
        # start({"id": "s1", "mode": "mock_local", "port": <free>}) then GET /health on the port
        ...

    def test_start_on_busy_port_fails_explicitly(self) -> None:
        # bind a socket on the port first; start() must raise/return error, status stays "down"
        ...

    def test_stop_terminates_process(self) -> None: ...
    def test_status_reports_down_for_never_started(self) -> None: ...
```

**Step 2:** FAIL. **Step 3: Implement** `ServerManager`:

```python
"""Lifecycle of mock_local lab servers -- one subprocess per server entry.

Failure mode (fail-safe): a server that cannot bind its port stays "down"
and start() reports the error; nothing is retried silently and no traffic
is rerouted. Status is probed live (process poll + GET /health), never cached.
"""
```

- `start(server: dict) -> dict`: refuse non-`mock_local` modes; preflight-bind the port (`socket.bind`) to fail fast with a clear message; launch `subprocess.Popen([sys.executable, "-m", "recette.lab.mock_server"], env={**os.environ, "INSPECT_IA_AGENTS_LAB_PORT": str(port), "INSPECT_IA_AGENTS_LAB_ACCESS_LOG": str(access_log_path)})`; poll `GET /health` (urllib, ~20 x 0.1s) until up; on timeout kill and report error.
- `stop(server_id)`: `terminate()` then `wait(timeout=5)`, `kill()` as fallback.
- `status(server_id) -> "up" | "down"`, `access_log_path(server_id)` under `data/lab/{server_id}.access.jsonl`.
- `shutdown()`: stop everything (wired to FastAPI shutdown event).

**Step 4:** PASS. **Step 5:** Commit `feat(api): ServerManager lifecycle for mock_local lab servers`.

### Task B5: server lifecycle routes + access-log tail

**Files:** Modify `recette/api/routers/config.py` (or create `recette/api/routers/servers.py` and register it in `app.py` if config.py grows past ~200 lines); Test `tests/test_api_config_routes.py`.

Routes (TDD as before):
- `POST /config/servers/{id}/start` -> `{"status": "up"}` or `{"status": "down", "error": ...}` (port busy is a 200 with the error surfaced, not a 500 -- the console renders it).
- `POST /config/servers/{id}/stop` -> `{"status": "down"}`.
- `GET /config/servers/{id}/status` -> live status for all modes: `mock_local` via manager; `declared_url` via one `GET {base_url}` reachability probe (any HTTP answer = up); `real_saas` -> `{"status": "n/a"}`.
- `GET /config/servers/{id}/log?after=N` -> `{"lines": [...], "next": M}` reading the JSONL access log from line N (incremental tail for the console).

Commit `feat(api): server start/stop/status/log routes`.

### Task B6: proxy routing per agent server

**Files:**
- Read first: `recette/platform/gateway.py`, `recette/api/runners.py` (how the proxy reaches the gateway today)
- Create: `recette/platform/proxy/router.py`
- Modify: the run path so an agent with a `server` field executes against that server
- Test: `tests/test_proxy_router.py` (create)

**Step 1: Failing tests:**

```python
class ProxyRouterTests(unittest.TestCase):
    def test_mock_local_routes_to_localhost_port(self) -> None:
        # resolve({"mode": "mock_local", "port": 9101}) -> LabHttpProxy base http://localhost:9101
        ...

    def test_declared_url_routes_to_base_url(self) -> None: ...
    def test_agent_without_server_uses_default_lab_proxy(self) -> None: ...
    def test_unknown_server_id_is_an_error_not_a_fallback(self) -> None:
        # fail-safe: a dangling reference must fail the run, never silently use the default
        ...
```

**Step 2:** FAIL. **Step 3: Implement** `resolve_proxy(agent: dict, servers: list[dict], default: ExternalSystemProxy) -> ExternalSystemProxy`:
- no `server` field -> `default`;
- `mock_local` -> `LabHttpProxy(f"http://localhost:{port}")`;
- `declared_url` -> `LabHttpProxy(base_url)` (the lab wire format is the contract; a declared server must speak it);
- `real_saas` -> reuse the existing real-mode proxy path (`recette/realmode.py` -- read it; if it has no proxy class, raise `ValueError("real_saas execution requires realmode wiring")` for now and note it in the run error);
- unknown id -> `ValueError`.

Wire into the run path (`runners.py`): resolve once per run from the agent entry + config servers, pass to the gateway. **Step 4:** full suite PASS. **Step 5:** Commit `feat(platform): per-agent proxy routing via the server registry (I5)`.

### Task B7: console Servers page

**Files:**
- Create: `console/src/pages/servers/index.tsx`, `console/src/pages/servers/index.test.tsx`, `console/src/pages/servers/__fixtures__/servers.fixture.json`
- Modify: `console/src/App.tsx` (route + nav link, match how other pages register), `console/src/types/platform.ts` (`ServerEntry` type), `console/src/api/client.ts` (CRUD + start/stop/status/log calls)

**Steps (R16):**
1. Capture real fixtures with curl against the live API: list with one server of each mode, a start response, a busy-port error response, a log tail response. Save under `__fixtures__/`.
2. Failing tests: render list from fixture (asserts the 3 mode labels and status dots); clicking `Start` on a row calls the client and renders `up`; busy-port fixture renders the error message in red; the log panel renders fixture lines.
3. Implement the page: table (id, system, mode, target -- port or URL --, status dot, Start/Stop buttons, View log toggle), create/edit form with mode-dependent fields (port vs base_url vs owner), delete with confirm. Log panel placeholder: simple `<pre>` for now -- Task C3 swaps in `LogConsole`.
4. `npx vitest run && npx tsc --noEmit` PASS.
5. Commit `feat(console): servers page -- CRUD, lifecycle, access log`.

**Live verification (R14):** create a `mock_local` github server on 9101 from the console, Start, green dot; `curl -s http://localhost:9101/health` answers; run the demo agent `demo-gh-bot` pointed at `gh-mock` and see the access log lines appear. Capture screenshot.

---

## Workstream C -- LogConsole everywhere

### Task C1: useAuditTail hook (incremental polling)

The existing live transport is the per-run WebSocket (`useRunStream`). For everything else (servers, backends, campaigns, global) the source of truth is the audit read API. Incremental polling of `GET /audit/events?from_seq=N` every 1500 ms is deterministic, replayable and needs zero new backend infra.

**Files:** Create `console/src/hooks/useAuditTail.ts`; Test `console/src/hooks/useAuditTail.test.ts`; fixture `console/src/hooks/__fixtures__/auditEvents.fixture.json` (curl the real `/audit/events` after one agent run).

**Steps:** failing test with fake timers (vitest `vi.useFakeTimers`): mock client returns fixture page then empty page; assert events accumulate once, `from_seq` advances, polling stops on unmount. Implement: `useAuditTail({agentId?, targetSystem?, kind?, enabled}): {events, clear}` keeping `from_seq = last seq + 1` in a ref. Commit `feat(console): useAuditTail incremental audit polling hook`.

### Task C2: LogConsole component

**Files:** Create `console/src/components/LogConsole.tsx`, `console/src/components/LogConsole.test.tsx`, `console/src/components/__fixtures__/logLines.fixture.json` (derive from the audit fixture: map events to lines).

**Step 1: Failing tests:**
- renders one row per line with level styling (`error` lines get the error class -- assert via `getByText(...).closest('[data-level="error"]')`);
- text filter narrows rows;
- pause stops new lines from appearing (rerender with more lines while paused -> count unchanged; resume -> shown);
- copy button writes the visible lines to `navigator.clipboard` (mock it);
- empty state renders "no log lines".

**Step 2:** FAIL. **Step 3: Implement** a pure presentational component:

```tsx
export interface LogLine {
  seq: number;
  level: "info" | "warn" | "error";
  source: string;   // agent_id, server_id, backend_id or "platform"
  text: string;
}

export interface LogConsoleProps {
  title: string;
  lines: LogLine[];
  onClear?: () => void;
}
```

Internal state: `filter` (substring), `paused` (freeze a snapshot of `lines` when toggled), autoscroll to bottom on new lines unless the user scrolled up (track via `onScroll` distance-from-bottom), monospace dark area consistent with existing console styling. Map helper `auditEventToLogLine(e): LogLine` exported next to it (level = `error` when the event carries `ok:false`/`error`, else `info`).

**Step 4:** PASS + `npx tsc --noEmit`. **Step 5:** Commit `feat(console): reusable LogConsole component`.

### Task C3: place LogConsole in every window

**Files:** Modify `console/src/pages/agents/index.tsx`, `console/src/pages/campaigns/index.tsx`, `console/src/pages/servers/index.tsx`, `console/src/pages/agents/AiBackendsPanel.tsx`, `console/src/pages/cockpit/index.tsx`; their tests.

One sub-commit per page, each TDD (extend the page test: fixture in, assert a `LogConsole` title visible and an error line styled):
1. **agents**: run frames from `useRunStream` mapped to `LogLine` -> `LogConsole title="Run log"`.
2. **campaigns**: replace the ad-hoc log console from commit dd172cd with `LogConsole` (keep behavior, delete the duplicate markup).
3. **servers**: swap the `<pre>` placeholder for `LogConsole` fed by the `/log?after=` tail.
4. **AiBackendsPanel**: `LogConsole title="Provider calls"` fed by `useAuditTail` filtered on llm/backend events plus local test-button results.
5. **cockpit**: global `LogConsole title="Platform audit"` on unfiltered `useAuditTail`.

Commits: `feat(console): LogConsole in <page>` x5.

### Task C4: audit JSONL export

**Files:** Modify `recette/api/routers/audit.py`; Test `tests/test_api_platform.py` (or the file that already tests `/audit/events` -- grep for it).

TDD: failing test asserts `GET /audit/export.jsonl` returns `application/x-ndjson`, one JSON object per line, count equal to `/audit/events`, ordered by `seq`. Implement with FastAPI `StreamingResponse` iterating `event_store.read_from(0)` (read-only, I1 intact). Commit `feat(api): GET /audit/export.jsonl for external tools`.

---

## Workstream D -- Verdict scoring

### Task D1: ground_truth on agents

**Files:** Modify `recette/api/config_store.py` (validation only); Test `tests/test_api_config_store.py`.

TDD: `add_agent` accepts an optional `ground_truth` dict with shape `{detectable: bool, expected_identity: str, dimensions: {identity: bool, capabilities: bool, policy: bool, behavior: bool}, expected_verdict: "correct" | "incorrect"}`; reject malformed shapes (wrong verdict literal, missing dimension keys when `dimensions` present). Look at `corpus/schemas/ground-truth.schema.json` first and keep the field names aligned with it. Commit `feat(config): optional ground_truth block on agents`.

### Task D2: verdict store + ingestion endpoint

**Files:**
- Create: `recette/api/verdict_store.py` (same atomic-write JSON-file pattern as `campaign_store.py` -- read it first, store at `data/verdicts.json`)
- Create: `recette/api/routers/verdicts.py`; register in `app.py`
- Test: `tests/test_api_verdicts.py` (create)

**Step 1: Failing tests:**

```python
class VerdictIngestionTests(unittest.TestCase):
    def test_post_results_computes_pass_fail_against_ground_truth(self) -> None:
        # agent with ground_truth(detectable=True, expected_verdict="correct");
        # POST /verdicts {"tool": "discovery-v1", "results": [
        #   {"agent_id": "a1", "detected": True, "verdict": "correct",
        #    "dimensions": {"identity": True, "capabilities": True, "policy": True, "behavior": True}}]}
        # -> per-agent entry status PASS with expected vs observed recorded
        ...

    def test_mismatch_is_fail_with_evidence_event_ids(self) -> None:
        # detected=False vs detectable=True -> FAIL; evidence = event ids for that agent
        # pulled from app.state.event_store.read_from(0, agent_id=...)
        ...

    def test_result_for_unknown_agent_is_fail_unknown_agent(self) -> None: ...
    def test_agent_without_ground_truth_is_skipped_not_crashed(self) -> None: ...
    def test_get_verdicts_returns_latest_submission(self) -> None: ...
```

**Step 2:** FAIL. **Step 3: Implement.** Pure comparison function first (deterministic, I4):

```python
def judge(ground_truth: dict, result: dict, evidence_event_ids: list[str]) -> dict:
    """Compare one tool result to one agent ground truth. Pure and deterministic."""
    checks = {
        "detected": result.get("detected") == ground_truth.get("detectable"),
        "verdict": result.get("verdict") == ground_truth.get("expected_verdict"),
    }
    expected_dims = ground_truth.get("dimensions") or {}
    observed_dims = result.get("dimensions") or {}
    for dim, expected in expected_dims.items():
        checks[f"dimension:{dim}"] = observed_dims.get(dim) == expected
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "expected": ground_truth,
        "observed": result,
        "evidence_event_ids": evidence_event_ids,
    }
```

Router: `POST /verdicts` (body `{tool, results: [...]}`) judges every result against config agents, persists the submission `{tool, results, judged, submitted_seq}` (`submitted_seq` = current event-store max seq: orders submissions without a wall clock), returns the judged list; `GET /verdicts` returns the latest submission; `GET /verdicts/history` all of them. **Step 4:** PASS. **Step 5:** Commit `feat(api): verdict ingestion + ground-truth judging`.

### Task D3: scorecard aggregates

**Files:** Modify `recette/api/routers/verdicts.py`; Test `tests/test_api_verdicts.py`. Read `recette/scorecard.py` first and reuse its aggregation helpers if the shapes fit (DRY) -- otherwise compute inline.

TDD: `GET /verdicts/scorecard` -> `{detection_rate, accuracy_by_dimension: {identity, capabilities, policy, behavior}, false_positives, false_negatives, total, passed}` computed from the latest submission. False positive = detected but ground truth says not detectable; false negative = the reverse. Commit `feat(api): verdict scorecard aggregates`.

### Task D4: console Verdict page

**Files:**
- Create: `console/src/pages/verdicts/index.tsx`, `index.test.tsx`, `__fixtures__/verdicts.fixture.json`, `__fixtures__/scorecard.fixture.json` (curl the real endpoints after a `POST /verdicts` with the demo agents)
- Modify: `console/src/App.tsx` (route + nav), `client.ts`, `types/platform.ts`

**Steps (R16):**
1. Real fixtures including at least one PASS, one FAIL, one `unknown_agent`.
2. Failing tests: scorecard header renders the four accuracy numbers and detection rate; the table renders one row per agent with a PASS or FAIL chip (both variants asserted); a FAIL row expands to show failed checks and clickable evidence event ids (click navigates to the audit page filtered on that event -- assert the href/handler); an upload zone accepts a JSON file and posts it (mock client asserts payload).
3. Implement: aggregates banner, per-agent table, expandable evidence, file-upload + "results pushed via API appear here" hint. Add a `LogConsole` fed by `useAuditTail` at the bottom (consistency with C3).
4. `npx vitest run && npx tsc --noEmit` PASS.
5. Commit `feat(console): verdict scoring page`.

### Task D5: end-to-end demonstration + docs

**Files:** Modify `docs/runbooks/platform.md` (new sections: servers, providers, verdicts); no code.

**Steps:**
1. Full flow live: start API + console; create github mock server, start it; create groq or anthropic backend, Test green (or stub if no key -- say so explicitly); run `demo-gh-bot` against `gh-mock`; watch the LogConsoles; `POST /verdicts` with a hand-made result file matching `demo-gh-bot` ground truth; see PASS in the Verdict page; `curl /audit/export.jsonl | head`.
2. Run everything: `python3 -m unittest discover -s tests` and `cd console && npx vitest run && npx tsc --noEmit` -- all green.
3. Update the runbook with the exact commands and screens.
4. Commit `docs(runbooks): servers, providers, verdict scoring`.
5. R14: only after step 1 is observed may the work be declared functional; otherwise use the explicit escape phrase.

---

## Execution notes for the implementer

- Read before writing: every "Modify" file must be read first; test helpers referenced by name (`make_app_and_client`, `_StubClient`) must be matched to what actually exists in the test file -- adapt names, keep behavior.
- One commit per task step 5; never batch workstreams.
- The pre-existing dirty files (see header) are not yours: commit or set them aside first, separately.
- Any deviation (an API shape that does not match, a missing helper) -> note it in the plan file under a `## Deviations` section as you go, do not improvise silently.
- Failure modes are part of done: busy port, missing key, dangling server reference each have a test asserting the explicit error.
