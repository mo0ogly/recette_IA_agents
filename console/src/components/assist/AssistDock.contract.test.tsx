/**
 * R16 contract tests for the Copilote IA dock.
 *
 * Fixtures in __fixtures__/ were captured from the REAL backend (docker
 * compose api on :8090): assistChat = a live LLM exchange (source "llm"),
 * assistChatError = a live failure through an unreachable backend (source
 * "error"), assistSession = the session memory, aiBackends = the configured
 * backends list. Both variants of the AssistSource union are covered.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AiBackend } from "../../types/platform";
import type { AssistChatResponse, AssistSessionMemory } from "../../types/assist";

import aiBackendsFixture from "./__fixtures__/aiBackends.fixture.json";
import chatErrorFixture from "./__fixtures__/assistChatError.fixture.json";
import chatFixture from "./__fixtures__/assistChat.fixture.json";
import sessionFixture from "./__fixtures__/assistSession.fixture.json";

vi.mock("../../api/assistClient", () => ({
  getAssistSession: vi.fn(),
  postAssistChat: vi.fn(),
  postAssistHelp: vi.fn(),
  clearAssistSession: vi.fn(),
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, listAiBackends: vi.fn() };
});

import { listAiBackends } from "../../api/client";
import { clearAssistSession, getAssistSession, postAssistChat } from "../../api/assistClient";

import AssistDock from "./AssistDock";
import AssistProvider from "./AssistProvider";

const backends = aiBackendsFixture as AiBackend[];
const chatResponse = chatFixture as AssistChatResponse;
const chatErrorResponse = chatErrorFixture as AssistChatResponse;
const sessionMemory = sessionFixture as AssistSessionMemory;

function renderDock(): void {
  render(
    <AssistProvider>
      <AssistDock />
    </AssistProvider>,
  );
}

describe("AssistDock (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(listAiBackends).mockResolvedValue(backends);
    vi.mocked(getAssistSession).mockResolvedValue({ thread: [], insights: [] });
    vi.mocked(postAssistChat).mockResolvedValue(chatResponse);
    vi.mocked(clearAssistSession).mockResolvedValue(undefined);
  });

  it("renders the backend dropdown from the real backends payload", async () => {
    renderDock();
    const select = await screen.findByLabelText("Backend IA");
    await waitFor(() => {
      expect(select.querySelectorAll("option").length).toBe(backends.length);
    });
    // First configured backend becomes the default selection.
    expect((select as HTMLSelectElement).value).toBe(backends[0].id);
  });

  it("rehydrates the session memory captured from the real backend", async () => {
    vi.mocked(getAssistSession).mockResolvedValue(sessionMemory);
    renderDock();
    const thread = await screen.findByTestId("assist-chat-thread");
    // Every message of the captured session renders.
    expect(thread.querySelectorAll(".assist-msg").length).toBe(sessionMemory.thread.length);
    expect(thread.textContent).toContain(sessionMemory.thread[0].content);
  });

  it("sends a chat message and renders the source:llm reply", async () => {
    renderDock();
    const input = await screen.findByPlaceholderText("Votre question...");
    fireEvent.change(input, { target: { value: "Explique le dashboard" } });
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    await waitFor(() => expect(postAssistChat).toHaveBeenCalledTimes(1));
    const call = vi.mocked(postAssistChat).mock.calls[0][0];
    expect(call.message).toBe("Explique le dashboard");
    expect(call.backend_id).toBe(backends[0].id);
    expect(call.session_id).toMatch(/^s-/);
    // The authoritative thread from the response replaces local state.
    const thread = await screen.findByTestId("assist-chat-thread");
    await waitFor(() => {
      expect(thread.textContent).toContain(chatResponse.reply);
    });
  });

  it("renders a source:error turn from the real failure payload", async () => {
    vi.mocked(postAssistChat).mockResolvedValue(chatErrorResponse);
    renderDock();
    const input = await screen.findByPlaceholderText("Votre question...");
    fireEvent.change(input, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    const thread = await screen.findByTestId("assist-chat-thread");
    await waitFor(() => {
      const errorTurns = thread.querySelectorAll('.assist-msg[data-source="error"]');
      expect(errorTurns.length).toBeGreaterThan(0);
    });
    expect(thread.textContent).toContain("[erreur backend]");
  });

  it("collapses and persists the dock state", async () => {
    renderDock();
    const dock = await screen.findByTestId("assist-dock");
    expect(dock).toHaveAttribute("data-open", "true");
    fireEvent.click(screen.getByRole("button", { name: "Replier le Copilote IA" }));
    expect(screen.getByTestId("assist-dock")).toHaveAttribute("data-open", "false");
    expect(window.localStorage.getItem("assist.dock.open")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Ouvrir le Copilote IA" }));
    expect(screen.getByTestId("assist-dock")).toHaveAttribute("data-open", "true");
  });

  it("clears the session from the journal tab", async () => {
    vi.mocked(getAssistSession).mockResolvedValue(sessionMemory);
    renderDock();
    await screen.findByTestId("assist-chat-thread");
    fireEvent.click(screen.getByRole("button", { name: /Journal/ }));
    fireEvent.click(screen.getByRole("button", { name: "Effacer la session" }));
    await waitFor(() => expect(clearAssistSession).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Conversation" }));
    expect(await screen.findByTestId("assist-chat-empty")).toBeInTheDocument();
  });
});
