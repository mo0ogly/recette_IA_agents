/**
 * R16 contract tests for the Reperage observability-detection page.
 *
 * The fixtures are the captured RAW payloads (no envelope -- the endpoints answer
 * raw, exactly what getDetectSignatures / scanForObservability resolve with), so
 * the render-and-assert proves the page consumes the live contract shape without
 * crashing:
 *  - __fixtures__/detect-signatures.fixture.json (GET /detect/signatures, 12 tools)
 *  - __fixtures__/detect-scan.fixture.json        (POST /detect/scan result)
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DetectPage from "./index";
import { getDetectSignatures, scanForObservability } from "../../api/client";
import type { DetectScanResult, DetectSignatures } from "../../types/platform";
import signaturesFixture from "./__fixtures__/detect-signatures.fixture.json";
import scanFixture from "./__fixtures__/detect-scan.fixture.json";

vi.mock("../../api/client", () => ({
  getDetectSignatures: vi.fn(),
  scanForObservability: vi.fn(),
}));

// The endpoints answer raw; the tests feed the mocks the captured raw payloads.
const signatures = signaturesFixture as unknown as DetectSignatures;
const scanResult = scanFixture as unknown as DetectScanResult;

afterEach(() => {
  vi.clearAllMocks();
});

describe("DetectPage", () => {
  it("renders the signatures catalog with distinct category badges", async () => {
    vi.mocked(getDetectSignatures).mockResolvedValue(signatures);
    render(<DetectPage />);

    // A tracing tool renders with its tracing category badge.
    expect(await screen.findByTestId("detect-tool-Langfuse")).toBeInTheDocument();
    const langfuseCat = screen.getByTestId("detect-tool-cat-Langfuse");
    expect(langfuseCat).toHaveTextContent("tracing");
    expect(langfuseCat).toHaveClass("detect-cat-tracing");

    // The gateway tool renders with a DISTINCT category badge (gateway != tracing).
    expect(screen.getByTestId("detect-tool-Helicone")).toBeInTheDocument();
    const heliconeCat = screen.getByTestId("detect-tool-cat-Helicone");
    expect(heliconeCat).toHaveTextContent("gateway");
    expect(heliconeCat).toHaveClass("detect-cat-gateway");
    expect(heliconeCat).not.toHaveClass("detect-cat-tracing");

    // Tools are grouped by category; the live signature table spans the three
    // categories its tools fall in (tracing / gateway / eval).
    expect(screen.getByTestId("detect-group-tracing")).toBeInTheDocument();
    expect(screen.getByTestId("detect-group-gateway")).toBeInTheDocument();
    expect(screen.getByTestId("detect-group-eval")).toBeInTheDocument();

    // A needle (the literal evidence) renders for a tool.
    expect(screen.getByTestId("detect-tool-Helicone")).toHaveTextContent(
      "HELICONE_API_KEY",
    );
  });

  it("renders the scan matches with their evidence", async () => {
    vi.mocked(getDetectSignatures).mockResolvedValue(signatures);
    vi.mocked(scanForObservability).mockResolvedValue(scanResult);
    render(<DetectPage />);

    await screen.findByTestId("detect-catalog");

    fireEvent.change(screen.getByTestId("detect-scan-input"), {
      target: { value: "import agentops; from langfuse import Langfuse" },
    });
    fireEvent.click(screen.getByTestId("detect-scan-button"));

    // Both matches render with their tool + the matched needle as evidence.
    const matches = await screen.findByTestId("detect-matches");
    expect(matches).toBeInTheDocument();
    expect(screen.getByTestId("detect-match-AgentOps")).toBeInTheDocument();
    expect(screen.getByTestId("detect-match-Langfuse")).toBeInTheDocument();
    expect(
      screen.getByTestId("detect-match-evidence-AgentOps"),
    ).toHaveTextContent("agentops");
    expect(
      screen.getByTestId("detect-match-evidence-Langfuse"),
    ).toHaveTextContent("langfuse");

    expect(scanForObservability).toHaveBeenCalledWith(
      "import agentops; from langfuse import Langfuse",
    );
  });

  it("renders an empty state when the scan detects no tool (no crash)", async () => {
    vi.mocked(getDetectSignatures).mockResolvedValue(signatures);
    vi.mocked(scanForObservability).mockResolvedValue({ matches: [] });
    render(<DetectPage />);

    await screen.findByTestId("detect-catalog");

    fireEvent.change(screen.getByTestId("detect-scan-input"), {
      target: { value: "nothing observable here" },
    });
    fireEvent.click(screen.getByTestId("detect-scan-button"));

    expect(await screen.findByTestId("detect-scan-empty")).toHaveTextContent(
      "aucun outil detecte",
    );
    expect(screen.queryByTestId("detect-matches")).not.toBeInTheDocument();
  });

  it("surfaces a signatures fetch error inline (fail-safe)", async () => {
    vi.mocked(getDetectSignatures).mockRejectedValue(
      new Error("503 detect unavailable"),
    );
    render(<DetectPage />);

    await waitFor(() =>
      expect(screen.getByTestId("detect-error")).toHaveTextContent(
        "503 detect unavailable",
      ),
    );
  });
});
