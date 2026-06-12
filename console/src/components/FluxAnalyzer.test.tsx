/**
 * FluxAnalyzer tests (R16 contract gate).
 *
 * Fixture: the real captured audit events (auditEvents.fixture.json). Monaco
 * cannot run under jsdom, so @monaco-editor/react is mocked with a textarea
 * stub exposing the value prop; the real rendering is checked at the live
 * smoke stage. fluxAnalyzerContent (pure) is tested directly as well.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import auditFixture from "../hooks/__fixtures__/auditEvents.fixture.json";
import type { AuditEvent } from "../types/platform";
import { FluxAnalyzer, fluxAnalyzerContent } from "./FluxAnalyzer";

vi.mock("@monaco-editor/react", () => ({
  default: ({ value }: { value: string }) => (
    <textarea readOnly data-testid="monaco-stub" value={value} />
  ),
}));

const events = (auditFixture as unknown as { events: AuditEvent[] }).events;

describe("fluxAnalyzerContent", () => {
  it("serializes the selected event as pretty JSON in event mode", () => {
    const target = events[0];
    const content = fluxAnalyzerContent(events, target.seq, "event");
    expect(JSON.parse(content)).toEqual(target);
    // Pretty-printed: multi-line output.
    expect(content).toContain("\n");
  });

  it("falls back to a hint when nothing is selected", () => {
    const content = fluxAnalyzerContent(events, null, "event");
    expect(JSON.parse(content)).toHaveProperty("hint");
  });

  it("serializes the whole window as JSONL in stream mode", () => {
    const content = fluxAnalyzerContent(events, null, "stream");
    const lines = content.split("\n");
    expect(lines).toHaveLength(events.length);
    expect(JSON.parse(lines[0])).toEqual(events[0]);
  });
});

describe("FluxAnalyzer", () => {
  it("renders the selected event JSON in the (mocked) editor", async () => {
    render(<FluxAnalyzer events={events} selectedSeq={events[0].seq} mode="event" />);

    const stub = await screen.findByTestId("monaco-stub");
    expect(stub).toHaveValue(JSON.stringify(events[0], null, 2));
  });

  it("renders the JSONL stream in stream mode", async () => {
    render(<FluxAnalyzer events={events} selectedSeq={null} mode="stream" />);

    const stub = await screen.findByTestId("monaco-stub");
    expect((stub as HTMLTextAreaElement).value.split("\n")).toHaveLength(events.length);
  });
});
