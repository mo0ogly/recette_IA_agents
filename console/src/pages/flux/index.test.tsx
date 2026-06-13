/**
 * Flux page tests (R16 contract gate).
 *
 * Real captured payloads only: auditEvents.fixture.json (GET /audit/events)
 * and the agents fixture shared with the agents page (GET /config/agents).
 * The lazy MonacoJsonViewer is mocked (jsdom cannot host Monaco). Fake
 * timers everywhere: useAuditTail polls on an interval and uncontrolled
 * ticks would leak state updates past test teardown.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import auditFixture from "../../hooks/__fixtures__/auditEvents.fixture.json";
import agentsFixture from "../agents/__fixtures__/agents.fixture.json";
import type { AgentConfig, AuditEvent } from "../../types/platform";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listAgents: vi.fn(),
    listAuditEvents: vi.fn(),
  };
});

vi.mock("../../components/MonacoJsonViewer", () => ({
  default: ({ value }: { value: string }) => (
    <textarea readOnly data-testid="monaco-stub" value={value} />
  ),
}));

import { listAgents, listAuditEvents } from "../../api/client";
import FluxPage from "./index";

const events = (auditFixture as unknown as { events: AuditEvent[] }).events;
const agents = agentsFixture as unknown as AgentConfig[];

function renderAt(path: string): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <FluxPage />
    </MemoryRouter>,
  );
}

/** Flush the mount-time poll and effects under fake timers. */
async function flush(): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

function stubValue(): string {
  return (screen.getByTestId("monaco-stub") as HTMLTextAreaElement).value;
}

describe("FluxPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    vi.mocked(listAgents).mockResolvedValue(agents);
    vi.mocked(listAuditEvents).mockResolvedValueOnce(events).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("tails the flux and shows the hint before any selection", async () => {
    renderAt("/flux");
    await flush();

    // Tail lines land in the LogConsole.
    expect(screen.getByText(/action_denied/)).toBeInTheDocument();
    // Analyzer shows the no-selection hint.
    expect(stubValue()).toContain("hint");
  });

  it("clicking a log line selects the event into the analyzer", async () => {
    renderAt("/flux");
    await flush();

    await act(async () => {
      fireEvent.click(screen.getByText(/action_denied/));
    });

    expect(JSON.parse(stubValue())).toEqual(events[0]);
  });

  it("stream mode dumps the visible window as JSONL", async () => {
    renderAt("/flux");
    await flush();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "stream" }));
    });

    expect(stubValue().split("\n")).toHaveLength(events.length);
  });

  it("?seq= deep link pre-selects the event once the tail lands", async () => {
    renderAt(`/flux?seq=${events[0].seq}`);
    await flush();

    expect(JSON.parse(stubValue())).toEqual(events[0]);
    // The selected log line is highlighted.
    const line = document.querySelector('.logc-line[data-selected="true"]');
    expect(line).not.toBeNull();
  });

  it("agent filter feeds the tail hook from the deep link", async () => {
    const knownAgent = agents[0].id;
    renderAt(`/flux?agent_id=${knownAgent}`);
    await flush();

    expect(vi.mocked(listAuditEvents).mock.calls[0][0]).toMatchObject({
      agent_id: knownAgent,
    });
    // The select reflects the filter (real agents fixture supplies the option).
    expect(screen.getByRole("combobox")).toHaveValue(knownAgent);
  });

  it("export button downloads the visible window as a bounded JSONL blob", async () => {
    // jsdom has no createObjectURL/revokeObjectURL: install fakes on the real
    // URL global (spreading URL into a stub would break the constructor).
    const createObjectURL = vi.fn().mockReturnValue("blob:flux");
    const revokeObjectURL = vi.fn();
    const urlGlobal = URL as unknown as Record<string, unknown>;
    const saved = {
      create: urlGlobal["createObjectURL"],
      revoke: urlGlobal["revokeObjectURL"],
    };
    urlGlobal["createObjectURL"] = createObjectURL;
    urlGlobal["revokeObjectURL"] = revokeObjectURL;
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    try {
      renderAt("/flux");
      await flush();

      fireEvent.click(screen.getByRole("button", { name: "Export window (JSONL)" }));

      expect(createObjectURL).toHaveBeenCalledTimes(1);
      const blob = createObjectURL.mock.calls[0][0] as Blob;
      expect(blob.type).toBe("application/x-ndjson");
      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:flux");
    } finally {
      clickSpy.mockRestore();
      urlGlobal["createObjectURL"] = saved.create;
      urlGlobal["revokeObjectURL"] = saved.revoke;
    }
  });
});
