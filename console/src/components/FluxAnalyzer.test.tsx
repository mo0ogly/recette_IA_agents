/**
 * FluxAnalyzer tests (R16 contract gate).
 *
 * Fixture: the real captured audit events (auditEvents.fixture.json). Monaco
 * cannot run under jsdom, so the lazy MonacoJsonViewer module is mocked with
 * a textarea stub exposing the value prop; the real rendering is checked at
 * the live smoke stage. fluxAnalyzerContent (pure) is tested directly too.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import auditFixture from "../hooks/__fixtures__/auditEvents.fixture.json";
import type { AuditEvent } from "../types/platform";
import { FluxAnalyzer, fluxAnalyzerContent, STREAM_THROTTLE_MS } from "./FluxAnalyzer";
import type { FluxDecoration } from "./fluxModel";

vi.mock("./MonacoJsonViewer", () => ({
  // Stub exposes both the value and the decoration count (data-attr) so the
  // decorated-stream path is assertable without the Monaco runtime.
  default: ({ value, decorations = [] }: { value: string; decorations?: FluxDecoration[] }) => (
    <textarea
      readOnly
      data-testid="monaco-stub"
      data-deco-count={decorations.length}
      data-deco-classes={decorations.map((d) => d.className ?? "").join(",")}
      value={value}
    />
  ),
}));

vi.mock("./MonacoDiffViewer", () => ({
  default: ({ original, modified }: { original: string; modified: string }) => (
    <div data-testid="diff-stub" data-original={original} data-modified={modified} />
  ),
}));

const events = (auditFixture as unknown as { events: AuditEvent[] }).events;

describe("fluxAnalyzerContent", () => {
  it("serializes the selected event as pretty JSON in event mode", () => {
    const target = events[0];
    const content = fluxAnalyzerContent(events, target.seq, "event");
    // Exact serialization, not just a parse round-trip (catches key drops).
    expect(content).toBe(JSON.stringify(target, null, 2));
  });

  it("falls back to a hint when nothing is selected", () => {
    const content = fluxAnalyzerContent(events, null, "event");
    expect(JSON.parse(content)).toHaveProperty("hint");
  });

  it("serializes the whole window as JSONL in stream mode, canonical key order", () => {
    const content = fluxAnalyzerContent(events, null, "stream");
    const lines = content.split("\n");
    expect(lines).toHaveLength(events.length);
    expect(JSON.parse(lines[0])).toEqual(events[0]);
    // Canonical top-level key order (nested objects like payload preserved):
    // reorder top-level keys only, not via an array replacer (which filters
    // keys at every depth and would strip payload's inner fields).
    const first = events[0] as unknown as Record<string, unknown>;
    const ordered = Object.fromEntries(
      Object.keys(first)
        .sort()
        .map((k) => [k, first[k]]),
    );
    expect(lines[0]).toBe(JSON.stringify(ordered));
  });

  it("shows a hint for an empty stream window", () => {
    expect(JSON.parse(fluxAnalyzerContent([], null, "stream"))).toHaveProperty("hint");
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

  it("passes governance decorations to the viewer in stream mode", async () => {
    render(<FluxAnalyzer events={events} selectedSeq={null} mode="stream" />);

    const stub = await screen.findByTestId("monaco-stub");
    // All three fixture events carry a verdict or approval signal -> decorated.
    expect(stub).toHaveAttribute("data-deco-count", String(events.length));
    expect(stub.getAttribute("data-deco-classes")).toContain("flux-verdict-deny");
  });

  it("applies the stream filter before serializing", async () => {
    render(
      <FluxAnalyzer
        events={events}
        selectedSeq={null}
        mode="stream"
        filter={{ minRisk: 3 }}
      />,
    );

    const stub = await screen.findByTestId("monaco-stub");
    // minRisk=3 drops seq 3 (no risk_score): 2 lines, 2 decorations.
    expect((stub as HTMLTextAreaElement).value.split("\n")).toHaveLength(2);
    expect(stub).toHaveAttribute("data-deco-count", "2");
  });

  it("renders a side-by-side diff of the two chosen events", async () => {
    render(
      <FluxAnalyzer
        events={events}
        selectedSeq={null}
        mode="diff"
        diffSeqs={[events[0].seq, events[1].seq]}
      />,
    );

    const diff = await screen.findByTestId("diff-stub");
    expect(diff).toHaveAttribute("data-original", JSON.stringify(events[0], null, 2));
    expect(diff).toHaveAttribute("data-modified", JSON.stringify(events[1], null, 2));
  });

  it("shows a hint on the diff side that is not chosen yet", async () => {
    render(<FluxAnalyzer events={events} selectedSeq={null} mode="diff" diffSeqs={[null, null]} />);

    const diff = await screen.findByTestId("diff-stub");
    expect(JSON.parse(diff.getAttribute("data-original") ?? "{}")).toHaveProperty("hint");
  });

  it("keeps decorations line-aligned with the throttled stream text", async () => {
    // Regression: the stream text is throttled (2 s) but decorations used to be
    // passed un-throttled, so a tail append could light lines the displayed
    // (older) buffer did not yet contain. Text + decorations are now throttled
    // as one model. A rerender that grows the tail happens within the throttle
    // window (the test runs in well under STREAM_THROTTLE_MS), so the displayed
    // value stays the OLD one -- and both fields move together: the decoration
    // count tracks the displayed line count instead of jumping ahead.
    expect(STREAM_THROTTLE_MS).toBeGreaterThan(100);
    const { rerender } = render(
      <FluxAnalyzer events={events.slice(0, 1)} selectedSeq={null} mode="stream" />,
    );
    const initial = (await screen.findByTestId("monaco-stub")) as HTMLTextAreaElement;
    expect(initial.value.split("\n")).toHaveLength(1);
    expect(initial.getAttribute("data-deco-count")).toBe("1");

    // Tail grows to the full window; still inside the throttle interval.
    rerender(<FluxAnalyzer events={events} selectedSeq={null} mode="stream" />);
    const mid = screen.getByTestId("monaco-stub") as HTMLTextAreaElement;
    const midLines = mid.value.split("\n").length;
    const midDecos = Number(mid.getAttribute("data-deco-count"));
    // Lockstep: decorations never reference more lines than are displayed.
    expect(midDecos).toBe(midLines);
  });
});
