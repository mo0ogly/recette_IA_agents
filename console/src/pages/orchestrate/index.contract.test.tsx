/**
 * R16 contract test for the Orchestration page.
 *
 * The fixture in __fixtures__/orchestrate.fixture.json was captured from the
 * real backend (recette.api via TestClient, build_llm patched to StubLlm), not
 * invented. The api client is mocked so the page renders against the exact
 * payload shape the backend returns: driving a team yields a verdict + run +
 * instances, and each acting instance deep-links into the wire packet list.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import fixture from "./__fixtures__/orchestrate.fixture.json";

vi.mock("../../api/client", () => ({
  runOrchestration: vi.fn(),
  listOrchestrationSessions: vi.fn(),
}));

import { listOrchestrationSessions, runOrchestration } from "../../api/client";
import OrchestratePage from "./index";

const runFixture = fixture.run as Awaited<ReturnType<typeof runOrchestration>>;
const sessionsFixture = fixture.sessions as Awaited<
  ReturnType<typeof listOrchestrationSessions>
>;

function renderPage(): void {
  render(
    <MemoryRouter>
      <OrchestratePage />
    </MemoryRouter>,
  );
}

describe("OrchestratePage (R16 contract)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listOrchestrationSessions).mockResolvedValue(sessionsFixture);
    vi.mocked(runOrchestration).mockResolvedValue(runFixture);
  });

  it("renders the form without crashing on the real payload shape", async () => {
    renderPage();
    expect(await screen.findByTestId("orchestrate-page")).toBeInTheDocument();
    expect(screen.getByTestId("orchestrate-team")).toBeInTheDocument();
    // Sessions load on mount from the (unwrapped) sessions payload.
    await waitFor(() =>
      expect(screen.getByTestId("orchestrate-sessions")).toBeInTheDocument(),
    );
  });

  it("drives a run and shows the verdict, hops and instance deep-links", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("orchestrate-run"));
    const verdict = await screen.findByTestId("orchestrate-verdict");
    expect(verdict).toHaveTextContent(runFixture.verdict);
    // Each acting instance deep-links into the wire packet list filtered to it.
    for (const iid of runFixture.instances) {
      const chip = screen.getByTestId(`orchestrate-instance-${iid}`);
      expect(chip).toHaveAttribute("href", expect.stringContaining(`instance=${iid}`));
      expect(chip.getAttribute("href")).toContain(`session=${runFixture.session_id}`);
    }
    // The routed hops are rendered.
    const hops = screen.getByTestId("orchestrate-hops");
    expect(within(hops).getAllByRole("listitem").length).toBe(runFixture.run.hops.length);
    // The wire-capture state is surfaced (the fixture was captured overlay-up).
    const wire = screen.getByTestId("orchestrate-wire");
    expect(wire).toHaveAttribute("data-captured", String(runFixture.wire_captured));
  });

  it("surfaces a client-side JSON parse error without calling the API", async () => {
    renderPage();
    const ta = await screen.findByTestId("orchestrate-team");
    fireEvent.change(ta, { target: { value: "{ not json" } });
    fireEvent.click(screen.getByTestId("orchestrate-run"));
    expect(await screen.findByTestId("orchestrate-error")).toHaveTextContent("invalide");
    expect(runOrchestration).not.toHaveBeenCalled();
  });

  it("surfaces a backend error (e.g. missing provider key)", async () => {
    vi.mocked(runOrchestration).mockRejectedValue(new Error("missing GROQ_API_KEY"));
    renderPage();
    fireEvent.click(await screen.findByTestId("orchestrate-run"));
    expect(await screen.findByTestId("orchestrate-error")).toHaveTextContent(
      "missing GROQ_API_KEY",
    );
  });
});
