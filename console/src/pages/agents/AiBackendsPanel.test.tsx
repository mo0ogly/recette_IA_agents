/**
 * R16 contract tests for the AI-backends panel.
 *
 * Fixtures in __fixtures__/ were captured from the real backend
 * (recette.api running locally against /config/ai-backends/{id}/test),
 * not invented. The api client module is mocked so the panel renders
 * against the exact payload shape the backend returns.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiBackend, BackendTestResult } from "../../types/platform";
import backendsFixture from "./__fixtures__/ai-backends.fixture.json";
import testOkFixture from "./__fixtures__/aiBackendTest.ok.fixture.json";
import testErrorFixture from "./__fixtures__/aiBackendTest.error.fixture.json";

vi.mock("../../api/client", () => ({
  createAiBackend: vi.fn(),
  deleteAiBackend: vi.fn(),
  testAiBackend: vi.fn(),
}));

import { createAiBackend, testAiBackend } from "../../api/client";
import AiBackendsPanel from "./AiBackendsPanel";

const backends = backendsFixture as unknown as AiBackend[];
const testOk = testOkFixture as unknown as BackendTestResult;
const testError = testErrorFixture as unknown as BackendTestResult;

const ALL_PROVIDERS = [
  "anthropic",
  "openai",
  "gemini",
  "groq",
  "mistral",
  "deepseek",
  "xai",
  "openai_compat",
];

function renderPanel(): { onChanged: () => void; onError: (m: string) => void } {
  const onChanged = vi.fn();
  const onError = vi.fn();
  render(
    <AiBackendsPanel backends={backends} onChanged={onChanged} onError={onError} />,
  );
  return { onChanged, onError };
}

describe("AiBackendsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("test button: ok fixture renders a green dot and the latency", async () => {
    vi.mocked(testAiBackend).mockResolvedValue(testOk);
    renderPanel();

    // Before any test the row dot is grey/untested.
    const row = screen.getByText("backend-1").closest("tr") as HTMLTableRowElement;
    expect(within(row).getByTestId("backend-test-status")).toHaveAttribute(
      "data-status",
      "untested",
    );

    fireEvent.click(within(row).getByRole("button", { name: "Test" }));

    expect(await within(row).findByText("17 ms")).toBeInTheDocument();
    expect(within(row).getByTestId("backend-test-status")).toHaveAttribute(
      "data-status",
      "ok",
    );
    expect(testAiBackend).toHaveBeenCalledWith("backend-1");
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
  });

  it("provider select lists all 8 providers", () => {
    renderPanel();

    const select = screen.getByLabelText("Provider");
    const values = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(values).toEqual(ALL_PROVIDERS);
  });

  it("base_url input appears only for openai_compat", () => {
    renderPanel();

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
});
