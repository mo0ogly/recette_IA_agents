/**
 * FluxAnalyzer tests (R16 contract gate).
 *
 * Fixture: the real captured audit events (auditEvents.fixture.json). Monaco
 * cannot run under jsdom, so the lazy MonacoJsonViewer module is mocked with
 * a textarea stub exposing the value prop; the real rendering is checked at
 * the live smoke stage. fluxAnalyzerContent (pure) is tested directly too.
 */

import { act, render, screen } from "@testing-library/react";
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
    // Regression: the stream text is throttled (STREAM_THROTTLE_MS) but the
    // decorations used to be passed un-throttled, so a tail append could light
    // lines the displayed (older) buffer did not yet contain. Text and
    // decorations are now one throttled model, so the displayed decoration
    // count always tracks the displayed line count -- before AND after the
    // throttle fires.
    //
    // shouldAdvanceTime lets real time elapse (so the lazy MonacoJsonViewer
    // import and testing-library's async polling resolve) while still allowing
    // advanceTimersByTime to drive the throttle deterministically -- the
    // idiomatic way to combine fake timers with React.lazy/Suspense.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { rerender } = render(
        <FluxAnalyzer events={events.slice(0, 1)} selectedSeq={null} mode="stream" />,
      );
      const initial = (await screen.findByTestId("monaco-stub")) as HTMLTextAreaElement;
      expect(initial.value.split("\n")).toHaveLength(1);
      expect(initial.getAttribute("data-deco-count")).toBe("1");

      // Tail grows to the full window, still inside the throttle interval: the
      // displayed value stays the OLD one and both fields stay aligned.
      rerender(<FluxAnalyzer events={events} selectedSeq={null} mode="stream" />);
      const mid = screen.getByTestId("monaco-stub") as HTMLTextAreaElement;
      expect(Number(mid.getAttribute("data-deco-count"))).toBe(mid.value.split("\n").length);
      expect(mid.value.split("\n")).toHaveLength(1);

      // Once the throttle elapses, text and decorations converge together to
      // the full window -- never one ahead of the other.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(STREAM_THROTTLE_MS);
      });
      const settled = screen.getByTestId("monaco-stub") as HTMLTextAreaElement;
      expect(settled.value.split("\n")).toHaveLength(events.length);
      expect(settled.getAttribute("data-deco-count")).toBe(String(events.length));
    } finally {
      vi.useRealTimers();
    }
  });
});
