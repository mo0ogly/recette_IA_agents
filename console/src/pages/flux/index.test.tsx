/**
 * Flux page tests (R16 contract gate).
 *
 * auditEvents.fixture.json was captured from a live GET /audit/events. The
 * page tails it through useAuditTail (client mocked at the module boundary,
 * resolving with the bare array the client contract returns) and feeds the
 * Monaco analyzer (mocked: jsdom cannot host the real editor).
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import auditFixture from "../../hooks/__fixtures__/auditEvents.fixture.json";
import type { AuditEvent } from "../../types/platform";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listAgents: vi.fn(),
    listAuditEvents: vi.fn(),
  };
});

vi.mock("@monaco-editor/react", () => ({
  default: ({ value }: { value: string }) => (
    <textarea readOnly data-testid="monaco-stub" value={value} />
  ),
}));

import { listAgents, listAuditEvents } from "../../api/client";
import FluxPage from "./index";

const events = (auditFixture as unknown as { events: AuditEvent[] }).events;

function renderAt(path: string): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <FluxPage />
    </MemoryRouter>,
  );
}

describe("FluxPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAgents).mockResolvedValue([]);
    vi.mocked(listAuditEvents).mockResolvedValueOnce(events).mockResolvedValue([]);
  });

  it("tails the flux and shows the hint before any selection", async () => {
    renderAt("/flux");

    // Tail lines land in the LogConsole.
    expect(await screen.findByText(/action_denied/)).toBeInTheDocument();
    // Analyzer shows the no-selection hint.
    const stub = await screen.findByTestId("monaco-stub");
    expect((stub as HTMLTextAreaElement).value).toContain("hint");
  });

  it("clicking a log line selects the event into the analyzer", async () => {
    renderAt("/flux");

    const firstLine = await screen.findByText(/action_denied/);
    await act(async () => {
      fireEvent.click(firstLine);
    });

    const stub = await screen.findByTestId("monaco-stub");
    const value = (stub as HTMLTextAreaElement).value;
    expect(JSON.parse(value)).toEqual(events[0]);
  });

  it("stream mode dumps the visible window as JSONL", async () => {
    renderAt("/flux");
    await screen.findByText(/action_denied/);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "stream" }));
    });

    const stub = await screen.findByTestId("monaco-stub");
    expect((stub as HTMLTextAreaElement).value.split("\n")).toHaveLength(events.length);
  });

  it("?seq= deep link pre-selects the event", async () => {
    renderAt(`/flux?seq=${events[0].seq}`);

    // The pre-selected event renders the text twice (log line + Monaco stub
    // payload), so a single-match query would race the pre-selection.
    await screen.findAllByText(/action_denied/);
    const stub = await screen.findByTestId("monaco-stub");
    expect(JSON.parse((stub as HTMLTextAreaElement).value)).toEqual(events[0]);
  });

  it("agent filter feeds the tail hook and the deep link", async () => {
    vi.mocked(listAgents).mockResolvedValue([
      { id: "fixture-bot", runtime: "lab", role: "developer", capability_scope: [] },
    ] as never);
    renderAt("/flux?agent_id=fixture-bot");

    await screen.findByText(/action_denied/);
    expect(vi.mocked(listAuditEvents).mock.calls[0][0]).toMatchObject({
      agent_id: "fixture-bot",
    });
  });
});
