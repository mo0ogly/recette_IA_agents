import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import LlmTracePanel from "./LlmTracePanel";
import type { LlmTrace, LlmTracesResult } from "../../api/client";
import fixture from "./__fixtures__/llm-traces.fixture.json";

const traces = (fixture as LlmTracesResult).traces as LlmTrace[];

describe("LlmTracePanel", () => {
  it("renders each captured decision with intent, tokens and latency", () => {
    render(<LlmTracePanel traces={traces} />);
    // a tool-call row shows its intent + total tokens + latency
    const row = screen.getByTestId("llm-trace-LC000001");
    expect(row).toHaveTextContent("read_repo:acme/x");
    expect(row).toHaveTextContent("153"); // 142 + 11 total_tokens
    expect(row).toHaveTextContent("512 ms");
    // the final "thought" row is labelled, not given a tool intent
    expect(screen.getByTestId("llm-trace-LC000003")).toHaveTextContent("(reflexion)");
  });

  it("shows an empty-state when no trace was captured", () => {
    render(<LlmTracePanel traces={[]} />);
    expect(screen.getByTestId("llm-trace-empty")).toBeInTheDocument();
  });
});
