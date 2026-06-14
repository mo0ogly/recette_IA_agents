/**
 * R16 contract gate for the promoted IA tab. The fixture in the Agents
 * __fixtures__/ folder was captured from the real GET /config/ai-backends
 * payload; the page must render it without crashing and surface the backend.
 */

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AiBackendsPage from "./index";
import type { AiBackend } from "../../types/platform";
import backendsFixture from "../agents/__fixtures__/ai-backends.fixture.json";

vi.mock("../../api/client", () => ({
  listAiBackends: vi.fn(),
  listAiProviders: vi.fn(),
  createAiBackend: vi.fn(),
  deleteAiBackend: vi.fn(),
  setBackendSecret: vi.fn(),
  deleteBackendSecret: vi.fn(),
  testAiBackend: vi.fn(),
}));

import { listAiBackends, listAiProviders } from "../../api/client";

const backends = backendsFixture as unknown as AiBackend[];

describe("AiBackendsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The embedded panel fetches the provider catalog on mount.
    vi.mocked(listAiProviders).mockResolvedValue([]);
  });

  it("renders the IA tab head and the backend from the real fixture", async () => {
    vi.mocked(listAiBackends).mockResolvedValue(backends);

    render(<AiBackendsPage />);

    // Page head proves the panel was promoted to its own tab.
    expect(screen.getByRole("heading", { name: "IA (backends)" })).toBeInTheDocument();
    // The help modal trigger must be present: when the panel was promoted to
    // its own tab the help was dropped, leaving the IA tab with no help. Guard
    // it so the regression cannot return silently.
    expect(
      screen.getByRole("button", { name: /Ouvrir l'aide : Aide — IA \(backends\)/ }),
    ).toBeInTheDocument();
    // The reused panel renders the fixture backend row (id + model are unique;
    // the provider name also appears in the create-form select, so assert on
    // the values that only exist in the row).
    expect(await screen.findByText("backend-1")).toBeInTheDocument();
    expect(screen.getByText("claude-opus-4-8")).toBeInTheDocument();
  });

  it("surfaces a load error in an alert banner", async () => {
    vi.mocked(listAiBackends).mockRejectedValue(new Error("boom"));

    render(<AiBackendsPage />);

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("boom");
  });
});
