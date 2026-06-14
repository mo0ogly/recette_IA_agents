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
  "bedrock",
  "openai_compat",
];

/** The catalog the mocked /config/ai-providers returns -- mirrors what the real
 * backend serves from recette.llm._PROVIDERS, so the dropdown lists every id. */
const PROVIDER_CATALOG: AiProviderInfo[] = ALL_PROVIDERS.map((id): AiProviderInfo => ({
  id,
  env_key: id === "openai_compat" ? null : `${id.toUpperCase()}_API_KEY`,
  key_required: id !== "openai_compat",
  base_url:
    id === "openai_compat" ? "required" : id === "bedrock" ? "optional" : null,
}));

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
});
