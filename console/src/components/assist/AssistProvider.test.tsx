/**
 * AssistProvider unit tests: session identity persistence, backend choice
 * persistence, and the help-flow journal consolidation (fixture payload).
 */

import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AssistHelpResponse } from "../../types/assist";

vi.mock("../../api/assistClient", () => ({
  getAssistSession: vi.fn(),
  postAssistChat: vi.fn(),
  postAssistHelp: vi.fn(),
  clearAssistSession: vi.fn(),
}));

import { getAssistSession, postAssistHelp } from "../../api/assistClient";

import AssistProvider, { useAssist } from "./AssistProvider";
import type { AssistContextValue } from "./AssistProvider";

function Capture({ onValue }: { onValue: (value: AssistContextValue) => void }): null {
  onValue(useAssist());
  return null;
}

function renderProvider(): { latest: () => AssistContextValue } {
  let value: AssistContextValue | null = null;
  render(
    <AssistProvider>
      <Capture
        onValue={(v) => {
          value = v;
        }}
      />
    </AssistProvider>,
  );
  return {
    latest: () => {
      if (value === null) {
        throw new Error("context not captured");
      }
      return value;
    },
  };
}

describe("AssistProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(getAssistSession).mockResolvedValue({ thread: [], insights: [] });
  });

  it("mints one session id and keeps it across mounts", async () => {
    const first = renderProvider();
    const sessionId = first.latest().sessionId;
    expect(sessionId).toMatch(/^s-/);
    expect(window.localStorage.getItem("assist.session.id")).toBe(sessionId);
    // A remount (page reload) reuses the same id -- the server-side memory key.
    const second = renderProvider();
    expect(second.latest().sessionId).toBe(sessionId);
  });

  it("persists the chosen backend id", async () => {
    const ctx = renderProvider();
    act(() => {
      ctx.latest().setBackendId("skynet-gpt-oss-120b");
    });
    expect(window.localStorage.getItem("assist.backend.id")).toBe("skynet-gpt-oss-120b");
    expect(ctx.latest().backendId).toBe("skynet-gpt-oss-120b");
  });

  it("consolidates a help answer into the insights journal", async () => {
    const helpResponse: AssistHelpResponse = {
      answer: "Le dashboard resume l'etat de la plateforme.",
      source: "llm",
      model: "openai/gpt-oss-120b",
      error: null,
      insight: {
        id: "i-1",
        topic: "dashboard.overview",
        label: "Vue d'ensemble",
        answer: "Le dashboard resume l'etat de la plateforme.",
        model: "openai/gpt-oss-120b",
        created_at: "2026-07-07T08:00:00Z",
      },
    };
    vi.mocked(postAssistHelp).mockResolvedValue(helpResponse);
    const ctx = renderProvider();
    act(() => {
      ctx.latest().setBackendId("skynet-gpt-oss-120b");
    });
    await act(async () => {
      await ctx.latest().askHelp("dashboard.overview", "Vue d'ensemble");
    });
    await waitFor(() => {
      expect(ctx.latest().insights).toHaveLength(1);
    });
    expect(ctx.latest().insights[0].topic).toBe("dashboard.overview");
    expect(ctx.latest().busyTopics.size).toBe(0);
  });

  it("refuses help without a backend and surfaces a hint", async () => {
    const ctx = renderProvider();
    await act(async () => {
      await ctx.latest().askHelp("dashboard.overview", "Vue d'ensemble");
    });
    expect(postAssistHelp).not.toHaveBeenCalled();
    expect(ctx.latest().lastError).toContain("backend IA");
  });
});
