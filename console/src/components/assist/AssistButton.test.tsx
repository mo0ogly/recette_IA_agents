/**
 * AssistButton tests: click -> POST /assist/help through the provider, the
 * journaled insight lands in the shared context, busy state on the button.
 * assistHelp.fixture.json was captured from the real docker API (a live
 * grounded answer on dashboard.overview through the skynet backend).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AssistHelpResponse } from "../../types/assist";

import helpFixture from "./__fixtures__/assistHelp.fixture.json";

vi.mock("../../api/assistClient", () => ({
  getAssistSession: vi.fn(),
  postAssistChat: vi.fn(),
  postAssistHelp: vi.fn(),
  clearAssistSession: vi.fn(),
}));

import { getAssistSession, postAssistHelp } from "../../api/assistClient";

import AssistButton from "./AssistButton";
import AssistProvider, { useAssist } from "./AssistProvider";

const helpResponse = helpFixture as AssistHelpResponse;

function JournalProbe(): JSX.Element {
  const assist = useAssist();
  return <div data-testid="journal-count">{assist.insights.length}</div>;
}

function renderButton(): void {
  render(
    <AssistProvider>
      <AssistButton
        topic="dashboard.overview"
        label="Vue d'ensemble du tableau de bord"
        params={{}}
      />
      <JournalProbe />
    </AssistProvider>,
  );
}

describe("AssistButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.localStorage.setItem("assist.backend.id", "skynet-gpt-oss-120b");
    vi.mocked(getAssistSession).mockResolvedValue({ thread: [], insights: [] });
    vi.mocked(postAssistHelp).mockResolvedValue(helpResponse);
  });

  it("carries the data-assist-topic locator anchor", () => {
    renderButton();
    const button = screen.getByRole("button", { name: "IA" });
    expect(button).toHaveAttribute("data-assist-topic", "dashboard.overview");
  });

  it("click sends the topic and journals the fixture insight", async () => {
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: "IA" }));
    await waitFor(() => expect(postAssistHelp).toHaveBeenCalledTimes(1));
    const call = vi.mocked(postAssistHelp).mock.calls[0][0];
    expect(call.topic).toBe("dashboard.overview");
    expect(call.backend_id).toBe("skynet-gpt-oss-120b");
    // The REAL captured insight is consolidated into the shared journal.
    await waitFor(() => {
      expect(screen.getByTestId("journal-count").textContent).toBe("1");
    });
  });

  it("shows the busy state while the call is in flight", async () => {
    let resolveCall: (value: AssistHelpResponse) => void = () => {};
    vi.mocked(postAssistHelp).mockReturnValue(
      new Promise<AssistHelpResponse>((resolve) => {
        resolveCall = resolve;
      }),
    );
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: "IA" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "IA..." })).toBeDisabled();
    });
    resolveCall(helpResponse);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "IA" })).toBeEnabled();
    });
  });
});
