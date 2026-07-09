/**
 * R16 contract tests for the AI-backends panel.
 *
 * Fixtures in __fixtures__/ were captured from the real backend
 * (recette.api running locally against /config/ai-backends/{id}/test),
 * not invented. The api client module is mocked so the panel renders
 * against the exact payload shape the backend returns.
 *
 * aiBackendTest.ok / aiBackendTest.prompt were captured from a real Groq
 * call (backend "groq-llama", model llama-3.3-70b-versatile) on 2026-06-13:
 * the no-prompt probe answered {"text":"pong"}, the prompt "what is 2+2"
 * answered {"text":"4"}. The provider key never appears in any payload (R8).
 */

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiBackend, BackendTestResult } from "../../types/platform";
import backendsFixture from "./__fixtures__/ai-backends.fixture.json";
import aiBackendsNoKeyFixture from "./__fixtures__/aiBackends.fixture.json";
import aiBackendsKeysetFixture from "./__fixtures__/aiBackends.keyset.fixture.json";
import setSecretFixture from "./__fixtures__/setSecret.fixture.json";
import testOkFixture from "./__fixtures__/aiBackendTest.ok.fixture.json";
import testErrorFixture from "./__fixtures__/aiBackendTest.error.fixture.json";
import testPromptFixture from "./__fixtures__/aiBackendTest.prompt.fixture.json";

vi.mock("../../api/client", () => ({
  createAiBackend: vi.fn(),
  deleteAiBackend: vi.fn(),
  testAiBackend: vi.fn(),
  setBackendSecret: vi.fn(),
  deleteBackendSecret: vi.fn(),
  listAiProviders: vi.fn(),
}));

import {
  createAiBackend,
  deleteBackendSecret,
  listAiProviders,
  setBackendSecret,
  testAiBackend,
} from "../../api/client";
import type { AiProviderInfo } from "../../types/platform";
import AiBackendsPanel from "./AiBackendsPanel";

const backends = backendsFixture as unknown as AiBackend[];
const backendsNoKey = aiBackendsNoKeyFixture as unknown as AiBackend[];
const backendsKeyset = aiBackendsKeysetFixture as unknown as AiBackend[];
const setSecretResult = setSecretFixture as { configured: boolean };
const testOk = testOkFixture as unknown as BackendTestResult;
const testError = testErrorFixture as unknown as BackendTestResult;
const testPrompt = testPromptFixture as unknown as BackendTestResult;

const ALL_PROVIDERS = [
  "anthropic",
  "openai",
  "gemini",
  "groq",
  "mistral",
  "deepseek",
  "xai",
  "openrouter",
  "together",
  "fireworks",
  "moonshot",
  "zai",
  "dashscope",
  "nvidia",
  "nous",
  "ollama_cloud",
  "novita",
  "stepfun",
  "arcee",
  "xiaomi",
  "gmi",
  "huggingface",
  "minimax",
  "minimax_cn",
  "opencode_zen",
  "kilocode",
  "alibaba_coding_plan",
  "qwen",
  "cerebras",
  "skynet",
  "bedrock",
  "openai_compat",
];

// SKYNET routes each chat model at its own URL; the catalog ships this map so the
// console auto-fills base_url when a model is picked (mirrors the backend).
const SKYNET_ENDPOINTS: Record<string, string> = {
  "openai/gpt-oss-120b": "https://api.skynet.cossi.internet/gpt-oss-120b/v1",
  "Foundation-Sec-8B-Reasoning-Q4_K_M.gguf": "https://api.skynet.cossi.internet/foundationsec/v1",
  "GLM-4.6V-Q4_K_M-00001-of-00002.gguf": "https://api.skynet.cossi.internet/glm46v/v1",
  "gemma-4-31B-it-BF16-00001-of-00002.gguf": "https://api.skynet.cossi.internet/gemma/v1",
  "qwen3.6-35b-a3b": "https://api.skynet.cossi.internet/qwen3.6/v1",
  "mistralai/Voxtral-Mini-3B-2507": "https://api.skynet.cossi.internet/voxtral/v1",
};

/** The catalog the mocked /config/ai-providers returns -- mirrors what the real
 * backend serves from recette.llm._PROVIDERS, so the dropdown lists every id. */
// Curated model dropdowns mirror recette.llm._PROVIDER_MODELS (intentionally
// partial: only providers with grounded model ids). Everything else falls back
// to a free-text model field (models: [], default_model: null).
const PROVIDER_MODELS: Record<string, string[]> = {
  anthropic: ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5", "claude-fable-5"],
  openai: ["gpt-4o", "gpt-4o-mini"],
  groq: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
  mistral: ["mistral-large-latest", "mistral-small-latest"],
  deepseek: ["deepseek-chat", "deepseek-reasoner"],
  cerebras: ["gpt-oss-120b", "zai-glm-4.7"],
  skynet: Object.keys(SKYNET_ENDPOINTS),
};

const PROVIDER_CATALOG: AiProviderInfo[] = ALL_PROVIDERS.map((id): AiProviderInfo => {
  const models = PROVIDER_MODELS[id] ?? [];
  return {
    id,
    env_key: id === "openai_compat" ? null : `${id.toUpperCase()}_API_KEY`,
    key_required: id !== "openai_compat",
    base_url:
      id === "openai_compat" || id === "skynet"
        ? "required"
        : id === "bedrock"
          ? "optional"
          : null,
    models,
    default_model: models.length > 0 ? models[0] : null,
    model_endpoints: id === "skynet" ? SKYNET_ENDPOINTS : {},
  };
});

function renderPanel(
  rows: AiBackend[] = backends,
): { onChanged: () => void; onError: (m: string) => void } {
  const onChanged = vi.fn();
  const onError = vi.fn();
  render(
    <AiBackendsPanel backends={rows} onChanged={onChanged} onError={onError} />,
  );
  return { onChanged, onError };
}

/** The key-status chip of a backend row (data-key-configured drives the test). */
function keyChip(id: string): HTMLElement {
  const row = screen.getByText(id).closest("tr") as HTMLTableRowElement;
  return within(row).getByTestId("backend-key-status");
}

describe("AiBackendsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAiProviders).mockResolvedValue(PROVIDER_CATALOG);
  });

  it("test button: ok fixture renders a green dot and the latency", async () => {
    vi.mocked(testAiBackend).mockResolvedValue(testOk);
    renderPanel();

    // The "Provider calls" LogConsole is mounted (empty) before any probe.
    expect(screen.getByText("Provider calls")).toBeInTheDocument();
    expect(screen.getByText("no log lines")).toBeInTheDocument();

    // Before any test the row dot is grey/untested.
    const row = screen.getByText("backend-1").closest("tr") as HTMLTableRowElement;
    expect(within(row).getByTestId("backend-test-status")).toHaveAttribute(
      "data-status",
      "untested",
    );

    fireEvent.click(within(row).getByRole("button", { name: "Test" }));

    expect(await within(row).findByText(/116 ms/)).toBeInTheDocument();
    expect(within(row).getByTestId("backend-test-status")).toHaveAttribute(
      "data-status",
      "ok",
    );
    // The model's one-word reply ("pong") is surfaced next to the latency,
    // proving a real round-trip rather than mere connectivity.
    expect(within(row).getByTestId("backend-test-reply")).toHaveTextContent('"pong"');
    expect(testAiBackend).toHaveBeenCalledWith("backend-1");

    // The probe outcome is appended to the console as an info-level line.
    const line = screen
      .getByText('backend backend-1 ok in 116 ms -- "pong"')
      .closest(".logc-line");
    expect(line).toHaveAttribute("data-level", "info");
  });

  it("test button: error fixture renders a red dot and the error text", async () => {
    vi.mocked(testAiBackend).mockResolvedValue(testError);
    renderPanel();

    const row = screen.getByText("backend-1").closest("tr") as HTMLTableRowElement;
    fireEvent.click(within(row).getByRole("button", { name: "Test" }));

    expect(
      await within(row).findByText(/GEMINI_API_KEY not set/),
    ).toBeInTheDocument();
    expect(within(row).getByTestId("backend-test-status")).toHaveAttribute(
      "data-status",
      "error",
    );

    // The failed probe is appended to the console as an error-level line.
    const line = screen
      .getByText(/^backend backend-1 failed in 0 ms: GEMINI_API_KEY not set/)
      .closest(".logc-line");
    expect(line).toHaveAttribute("data-level", "error");
  });

  it("provider select lists every provider from the fetched catalog", async () => {
    renderPanel();

    const select = screen.getByLabelText("Provider");
    // The dropdown is populated from GET /config/ai-providers, so wait for the
    // fetch to resolve before asserting every id is present.
    await waitFor(() => {
      expect(within(select).getAllByRole("option")).toHaveLength(
        ALL_PROVIDERS.length,
      );
    });
    const values = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(values).toEqual(ALL_PROVIDERS);
    expect(listAiProviders).toHaveBeenCalled();
  });

  it("note copy is truthful: per-backend keys are stored write-only", () => {
    renderPanel();

    // Regression lock: the old note claimed the key is "never stored here",
    // which contradicts the per-backend write-only secret store. Assert the
    // false claim is gone and the truthful wording is present.
    expect(screen.queryByText(/never stored here/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/write-only: the console sends it but never reads it back/),
    ).toBeInTheDocument();
  });

  it("each row shows a visible 'Ask the model' caption for the ask affordance", () => {
    renderPanel();

    const row = screen.getByText("backend-1").closest("tr") as HTMLTableRowElement;
    expect(within(row).getByText("Ask the model")).toBeInTheDocument();
  });

  it("base_url input appears only for openai_compat", async () => {
    renderPanel();
    // Wait for the async provider catalog so the options (and base_url mode) exist.
    await screen.findByRole("option", { name: "openai_compat" });

    expect(screen.queryByLabelText("Base URL")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "openai_compat" },
    });
    expect(screen.getByLabelText("Base URL")).toHaveAttribute(
      "placeholder",
      "http://localhost:11434/v1",
    );

    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "anthropic" },
    });
    expect(screen.queryByLabelText("Base URL")).not.toBeInTheDocument();
  });

  it("create payload includes base_url only for openai_compat", async () => {
    vi.mocked(createAiBackend).mockResolvedValue({} as never);
    renderPanel();
    await screen.findByRole("option", { name: "openai_compat" });

    // openai_compat: base_url is part of the payload.
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "local" } });
    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "openai_compat" },
    });
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "m" } });
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "http://localhost:11434/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create backend" }));

    expect(createAiBackend).toHaveBeenCalledWith({
      id: "local",
      provider: "openai_compat",
      model: "m",
      base_url: "http://localhost:11434/v1",
    });

    // any other provider: no base_url key at all.
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "cloud" } });
    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "anthropic" },
    });
    fireEvent.change(screen.getByLabelText("Model"), {
      target: { value: "claude-opus-4-8" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create backend" }));

    expect(createAiBackend).toHaveBeenLastCalledWith({
      id: "cloud",
      provider: "anthropic",
      model: "claude-opus-4-8",
    });
  });

  it("after a successful create the form resets to the default provider's default model", async () => {
    vi.mocked(createAiBackend).mockResolvedValue({} as never);
    renderPanel();
    await waitFor(() => expect(listAiProviders).toHaveBeenCalled());

    // Switch to mistral (so the reset must actually move back to anthropic).
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "m1" } });
    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "mistral" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create backend" }));
    await waitFor(() => expect(createAiBackend).toHaveBeenCalled());

    // The form must reset to anthropic WITH its default model selected, not an
    // empty "custom" state (regression: setForm(EMPTY) left model empty).
    const provider = screen.getByLabelText("Provider") as HTMLSelectElement;
    expect(provider.value).toBe("anthropic");
    const model = screen.getByLabelText("Model") as HTMLSelectElement;
    expect(model.tagName).toBe("SELECT");
    expect(model.value).toBe("claude-opus-4-8");
    expect(screen.queryByLabelText("Custom model id")).not.toBeInTheDocument();
  });

  it("key_configured false renders a 'no key' chip and the Save-key input", () => {
    renderPanel(backendsNoKey);

    expect(keyChip("b1")).toHaveAttribute("data-key-configured", "false");
    expect(keyChip("b1")).toHaveTextContent("no key");

    // The write-only key input is present and password-typed (R8).
    const row = screen.getByText("b1").closest("tr") as HTMLTableRowElement;
    const input = within(row).getByLabelText("API key for b1");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("autocomplete", "off");

    // No "Remove key" button when no key is configured.
    expect(
      within(row).queryByRole("button", { name: "Remove key" }),
    ).not.toBeInTheDocument();
  });

  it("typing a key and saving calls setBackendSecret, clears the input and refreshes", async () => {
    vi.mocked(setBackendSecret).mockResolvedValue(setSecretResult);
    // After a successful save the panel refreshes the list; the parent re-renders
    // with the keyset fixture. We simulate that by re-rendering on onChanged.
    const onChanged = vi.fn();
    const onError = vi.fn();
    const { rerender } = render(
      <AiBackendsPanel
        backends={backendsNoKey}
        onChanged={onChanged}
        onError={onError}
      />,
    );

    const row = screen.getByText("b1").closest("tr") as HTMLTableRowElement;
    const input = within(row).getByLabelText("API key for b1") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "test-not-real-key" } });
    fireEvent.click(within(row).getByRole("button", { name: "Save key" }));

    await waitFor(() =>
      expect(setBackendSecret).toHaveBeenCalledWith("b1", "test-not-real-key"),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    // Let the post-save state updates (clear draft + saved hint) flush.
    await screen.findByTestId("backend-key-saved");

    // The parent refresh flips key_configured to true.
    rerender(
      <AiBackendsPanel
        backends={backendsKeyset}
        onChanged={onChanged}
        onError={onError}
      />,
    );

    expect(keyChip("b1")).toHaveAttribute("data-key-configured", "true");
    expect(keyChip("b1")).toHaveTextContent("key set");

    // The input was cleared after the successful save (no key lingers in state).
    const clearedRow = screen.getByText("b1").closest("tr") as HTMLTableRowElement;
    const clearedInput = within(clearedRow).getByLabelText(
      "API key for b1",
    ) as HTMLInputElement;
    expect(clearedInput.value).toBe("");
  });

  it("the typed key value never appears in the rendered DOM after save", async () => {
    vi.mocked(setBackendSecret).mockResolvedValue(setSecretResult);
    renderPanel(backendsNoKey);

    const row = screen.getByText("b1").closest("tr") as HTMLTableRowElement;
    const input = within(row).getByLabelText("API key for b1") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "super-secret-value" } });
    fireEvent.click(within(row).getByRole("button", { name: "Save key" }));

    await waitFor(() => expect(setBackendSecret).toHaveBeenCalled());
    // The input is cleared by the post-save state update; wait for it to settle.
    await waitFor(() => expect(input.value).toBe(""));
    // Wait for the "saved" hint so every post-save state update has flushed
    // (avoids an act() warning from a late update after assertions).
    await screen.findByTestId("backend-key-saved");

    // The secret is write-only: it must not survive in any DOM text.
    expect(document.body.textContent).not.toContain("super-secret-value");
  });

  it("Save is disabled while the key input is empty", () => {
    renderPanel(backendsNoKey);

    const row = screen.getByText("b1").closest("tr") as HTMLTableRowElement;
    const save = within(row).getByRole("button", { name: "Save key" });
    expect(save).toBeDisabled();

    fireEvent.change(within(row).getByLabelText("API key for b1"), {
      target: { value: "x" },
    });
    expect(save).not.toBeDisabled();
  });

  it("key_configured true shows 'Remove key' which calls deleteBackendSecret after confirm", async () => {
    vi.mocked(deleteBackendSecret).mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onChanged } = renderPanel(backendsKeyset);

    expect(keyChip("b1")).toHaveAttribute("data-key-configured", "true");

    const row = screen.getByText("b1").closest("tr") as HTMLTableRowElement;
    fireEvent.click(within(row).getByRole("button", { name: "Remove key" }));

    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => expect(deleteBackendSecret).toHaveBeenCalledWith("b1"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    confirmSpy.mockRestore();
  });

  it("Remove key does nothing when the user cancels the confirm", () => {
    vi.mocked(deleteBackendSecret).mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPanel(backendsKeyset);

    const row = screen.getByText("b1").closest("tr") as HTMLTableRowElement;
    fireEvent.click(within(row).getByRole("button", { name: "Remove key" }));

    expect(deleteBackendSecret).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("ask: typing a prompt and clicking Ask sends it and renders the answer", async () => {
    vi.mocked(testAiBackend).mockResolvedValue(testPrompt);
    renderPanel();

    const row = screen.getByText("backend-1").closest("tr") as HTMLTableRowElement;
    const input = within(row).getByLabelText(
      "Ask the model behind backend-1",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "what is 2+2" } });
    fireEvent.click(within(row).getByRole("button", { name: "Ask" }));

    // The prompt is threaded to the client unchanged.
    expect(testAiBackend).toHaveBeenCalledWith("backend-1", "what is 2+2");

    // The model's answer ("4") is rendered in the response area.
    const answer = await within(row).findByTestId("backend-ask-answer");
    expect(answer).toHaveAttribute("data-status", "ok");
    expect(answer).toHaveTextContent("4");
    expect(answer).toHaveTextContent("141 ms");

    // The prompt and the model answer are also surfaced in the "Provider
    // calls" console so responses are readable in one place.
    const console = screen.getByText("Provider calls").closest("section") as HTMLElement;
    expect(within(console).getByText(/ask> what is 2\+2/)).toBeInTheDocument();
    expect(within(console).getByText(/^4 \(141 ms\)$/)).toBeInTheDocument();
  });

  it("ask: an error response renders in the red error area", async () => {
    vi.mocked(testAiBackend).mockResolvedValue(testError);
    renderPanel();

    const row = screen.getByText("backend-1").closest("tr") as HTMLTableRowElement;
    fireEvent.change(
      within(row).getByLabelText("Ask the model behind backend-1"),
      { target: { value: "hello" } },
    );
    fireEvent.click(within(row).getByRole("button", { name: "Ask" }));

    const answer = await within(row).findByTestId("backend-ask-answer");
    expect(answer).toHaveAttribute("data-status", "error");
    expect(answer).toHaveTextContent(/GEMINI_API_KEY not set/);
    expect(answer.className).toContain("agents-ask-error");
  });

  it("ask: the Ask button is disabled while the prompt input is empty", () => {
    renderPanel();

    const row = screen.getByText("backend-1").closest("tr") as HTMLTableRowElement;
    const ask = within(row).getByRole("button", { name: "Ask" });
    expect(ask).toBeDisabled();

    fireEvent.change(
      within(row).getByLabelText("Ask the model behind backend-1"),
      { target: { value: "hi" } },
    );
    expect(ask).not.toBeDisabled();
  });

  it("preset: LiteLLM gateway fills provider=openai_compat + base_url + model", async () => {
    renderPanel();
    // The provider catalog must have loaded so openai_compat shows its base_url field.
    await waitFor(() => expect(listAiProviders).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId("preset-litellm"));

    const provider = screen.getByLabelText("Provider") as HTMLSelectElement;
    expect(provider.value).toBe("openai_compat");
    const baseUrl = (await screen.findByLabelText("Base URL")) as HTMLInputElement;
    // Falls back to localhost:4000 when VITE_LLM_PROXY_URL is unset (test env).
    expect(baseUrl.value).toBe("http://localhost:4000");
    const model = screen.getByLabelText("Model") as HTMLInputElement;
    expect(model.value).toBe("groq-llama");
  });

  it("switching provider resets the model to the new provider's default", async () => {
    renderPanel();
    await waitFor(() => expect(listAiProviders).toHaveBeenCalled());

    // anthropic is the starting provider and is curated, so the model field is a
    // dropdown preset to anthropic's default.
    const model = (await screen.findByLabelText("Model")) as HTMLSelectElement;
    expect(model.tagName).toBe("SELECT");
    expect(model.value).toBe("claude-opus-4-8");

    // Switching to mistral must NOT keep an anthropic/other model selected: the
    // model resets to mistral's default (regression: a groq model used to linger
    // after switching provider).
    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "mistral" },
    });
    const mistralModel = screen.getByLabelText("Model") as HTMLSelectElement;
    expect(mistralModel.value).toBe("mistral-large-latest");
    const options = within(mistralModel)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(options).toContain("mistral-small-latest");
    expect(options).not.toContain("claude-opus-4-8");
  });

  it("skynet: model dropdown lists chat routes and auto-fills the per-model base_url", async () => {
    renderPanel();
    await waitFor(() => expect(listAiProviders).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "skynet" },
    });

    // base_url auto-filled from the default model's per-model endpoint.
    const baseUrl = (await screen.findByLabelText("Base URL")) as HTMLInputElement;
    expect(baseUrl.value).toBe("https://api.skynet.cossi.internet/gpt-oss-120b/v1");

    // The dropdown lists the 6 chat routes; the two non-chat routes are absent.
    const model = screen.getByLabelText("Model") as HTMLSelectElement;
    const options = within(model)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(options).toContain("openai/gpt-oss-120b");
    expect(options).toContain("qwen3.6-35b-a3b");
    expect(options).not.toContain("jinaai/jina-reranker-m0");

    // Picking another model re-points base_url to that model's route.
    fireEvent.change(model, { target: { value: "qwen3.6-35b-a3b" } });
    expect((screen.getByLabelText("Base URL") as HTMLInputElement).value).toBe(
      "https://api.skynet.cossi.internet/qwen3.6/v1",
    );

    // The SKYNET-specific help is shown.
    expect(screen.getByTestId("skynet-hint")).toBeInTheDocument();
  });

  it("curated dropdown offers a custom path that reveals a free-text input", async () => {
    renderPanel();
    await waitFor(() => expect(listAiProviders).toHaveBeenCalled());

    const model = (await screen.findByLabelText("Model")) as HTMLSelectElement;
    // No custom input until the custom sentinel is chosen.
    expect(screen.queryByLabelText("Custom model id")).not.toBeInTheDocument();

    fireEvent.change(model, { target: { value: "__custom__" } });
    const custom = screen.getByLabelText("Custom model id") as HTMLInputElement;
    expect(custom).toBeInTheDocument();
    fireEvent.change(custom, { target: { value: "mistral-tiny" } });
    expect(custom.value).toBe("mistral-tiny");
  });

  it("provider without curated models keeps a free-text model field", async () => {
    renderPanel();
    await waitFor(() => expect(listAiProviders).toHaveBeenCalled());

    // xai curates no model -> the field stays a plain text input.
    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "xai" },
    });
    const model = screen.getByLabelText("Model") as HTMLInputElement;
    expect(model.tagName).toBe("INPUT");
    expect(model.value).toBe("");
  });
});
