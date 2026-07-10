import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import LivePage from "./index";
import type { LiveSource } from "./index";
import fixture from "./__fixtures__/liveEvent.fixture.json";
import type { RealtimeStatus } from "../../types/platform";

/**
 * R16 contract gate: render LivePage against a REAL /events/stream payload
 * (captured in __fixtures__/liveEvent.fixture.json) fed through a fake
 * EventSource, plus an injected status fetcher. No live socket, deterministic.
 */

class FakeSource implements LiveSource {
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  closed = false;
  close(): void {
    this.closed = true;
  }
}

function renderLive(status: RealtimeStatus) {
  const source = new FakeSource();
  const statusFetcher = vi.fn(() => Promise.resolve(status));
  render(
    <MemoryRouter>
      <LivePage
        sourceFactory={() => source}
        statusFetcher={statusFetcher}
        statusIntervalMs={100000}
      />
    </MemoryRouter>,
  );
  return { source, statusFetcher };
}

const HEALTHY: RealtimeStatus = { degraded: false, pending: 0, dropped: 0 };

afterEach(() => {
  vi.clearAllMocks();
});

describe("LivePage", () => {
  it("shows the empty state before any event arrives", () => {
    renderLive(HEALTHY);
    expect(screen.getByTestId("live-empty")).toBeInTheDocument();
    expect(screen.getByTestId("live-connection")).toHaveTextContent("Deconnecte");
  });

  it("renders a row from a real diffused event and flips to Connecte", async () => {
    const { source } = renderLive(HEALTHY);
    act(() => {
      source.onopen?.(null);
      source.onmessage?.({ data: JSON.stringify(fixture) });
    });

    expect(screen.getByTestId("live-connection")).toHaveTextContent("Connecte");
    const rows = screen.getAllByTestId("live-row");
    expect(rows).toHaveLength(1);
    // Fields read from the real envelope payload.
    expect(screen.getByText("action_denied")).toBeInTheDocument();
    expect(screen.getByText(fixture.payload.agent_id as string)).toBeInTheDocument();
    expect(screen.getByText("okta/list_users")).toBeInTheDocument();
    // The verdict badge reads payload.policy_decision.verdict = "deny".
    expect(screen.getByText("deny")).toBeInTheDocument();
  });

  it("de-duplicates an event re-delivered with the same seq", () => {
    const { source } = renderLive(HEALTHY);
    act(() => {
      source.onmessage?.({ data: JSON.stringify(fixture) });
      source.onmessage?.({ data: JSON.stringify(fixture) });
    });
    expect(screen.getAllByTestId("live-row")).toHaveLength(1);
  });

  it("ignores a malformed frame without crashing", () => {
    const { source } = renderLive(HEALTHY);
    act(() => {
      source.onmessage?.({ data: "{not json" });
    });
    expect(screen.getByTestId("live-empty")).toBeInTheDocument();
  });

  it("surfaces a degraded transport from the status fetcher", async () => {
    renderLive({ degraded: true, pending: 5, dropped: 2 });
    await waitFor(() =>
      expect(screen.getByText("Bus degrade")).toBeInTheDocument(),
    );
    expect(screen.getByText(/En attente: 5/)).toBeInTheDocument();
  });

  // Discriminated-union coverage (R16): every PolicyVerdict and ApprovalState
  // variant must render its badge. Variants derive from the real captured
  // envelope, only the discriminant fields (and seq/event_id) change.
  describe.each([
    ["allow", "badge-allow"],
    ["escalate", "badge-escalate"],
  ] as const)("policy_decision verdict %s", (verdict, badgeClass) => {
    it(`renders the ${verdict} verdict badge`, () => {
      const { source } = renderLive(HEALTHY);
      const event = {
        ...fixture,
        seq: 42,
        event_id: `EV-verdict-${verdict}`,
        payload: {
          ...fixture.payload,
          policy_decision: { ...fixture.payload.policy_decision, verdict },
        },
      };
      act(() => {
        source.onmessage?.({ data: JSON.stringify(event) });
      });
      expect(screen.getByText(verdict)).toHaveClass("badge", badgeClass);
    });
  });

  describe.each([
    ["pending", "badge-pending"],
    ["approved", "badge-approved"],
    ["denied", "badge-denied"],
    ["timeout", "badge-timeout"],
  ] as const)("approval_state %s", (approval, badgeClass) => {
    it(`renders the ${approval} approval badge`, () => {
      const { source } = renderLive(HEALTHY);
      const event = {
        ...fixture,
        seq: 43,
        event_id: `EV-approval-${approval}`,
        payload: { ...fixture.payload, approval_state: approval },
      };
      act(() => {
        source.onmessage?.({ data: JSON.stringify(event) });
      });
      expect(screen.getByText(approval)).toHaveClass("badge", badgeClass);
    });
  });

  it("closes the source on unmount", () => {
    const source = new FakeSource();
    const { unmount } = render(
      <MemoryRouter>
        <LivePage
          sourceFactory={() => source}
          statusFetcher={() => Promise.resolve(HEALTHY)}
        />
      </MemoryRouter>,
    );
    unmount();
    expect(source.closed).toBe(true);
  });
});
