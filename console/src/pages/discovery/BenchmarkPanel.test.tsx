import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import BenchmarkPanel from "./BenchmarkPanel";
import { getBenchmark } from "../../api/client";
import type { Benchmark } from "../../api/client";
import fixture from "./__fixtures__/benchmark.fixture.json";

vi.mock("../../api/client", () => ({
  getBenchmark: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("BenchmarkPanel", () => {
  it("renders per-area and per-style accuracy from a real payload", async () => {
    vi.mocked(getBenchmark).mockResolvedValue(fixture as Benchmark);
    render(<BenchmarkPanel />);

    expect(await screen.findByTestId("benchmark-area-identification")).toBeInTheDocument();
    expect(screen.getByTestId("benchmark-area-orchestration")).toBeInTheDocument();
    // every orchestration style has its own accuracy row.
    for (const style of ["handoff", "sequential", "concurrent", "group_chat", "magentic"]) {
      expect(screen.getByTestId(`benchmark-style-${style}`)).toBeInTheDocument();
    }
    // accuracy is rendered as a percentage.
    expect(screen.getByTestId("benchmark-area-maf")).toHaveTextContent("100%");
  });

  it("shows an inline error when the fetch fails", async () => {
    vi.mocked(getBenchmark).mockRejectedValue(new Error("boom"));
    render(<BenchmarkPanel />);
    await waitFor(() => expect(screen.getByTestId("benchmark-error")).toHaveTextContent("boom"));
  });
});
