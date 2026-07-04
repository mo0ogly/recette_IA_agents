/**
 * VirtualList tests -- the hand-rolled windowed list used by the proxy panels.
 *
 * jsdom performs NO layout: scrollHeight/clientHeight are always 0 and
 * assigning scrollTop does not fire scroll events. The tests therefore pin
 * the scroll metrics with Object.defineProperty on the container and drive
 * the component with fireEvent.scroll; assertions stay on what the component
 * controls (the rendered window, the tail callback, the scrollTop assignment)
 * rather than on real browser scrolling.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VirtualList } from "./VirtualList";

interface Row {
  seq: number;
  label: string;
}

const ITEMS: Row[] = Array.from({ length: 1000 }, (_, i) => ({
  seq: i,
  label: `row-${i}`,
}));

function renderList(
  overrides: Partial<React.ComponentProps<typeof VirtualList<Row>>> = {},
): HTMLElement {
  render(
    <VirtualList<Row>
      items={ITEMS}
      rowHeight={20}
      height={200}
      renderRow={(item) => <span data-testid="vrow">{item.label}</span>}
      testId="vlist"
      {...overrides}
    />,
  );
  return screen.getByTestId("vlist");
}

/** Pin jsdom scroll metrics on the container (no layout engine in jsdom). */
function defineScrollMetrics(
  el: HTMLElement,
  metrics: { scrollTop?: number; scrollHeight?: number; clientHeight?: number },
): void {
  if (metrics.scrollTop !== undefined) {
    Object.defineProperty(el, "scrollTop", { value: metrics.scrollTop, writable: true });
  }
  if (metrics.scrollHeight !== undefined) {
    Object.defineProperty(el, "scrollHeight", { value: metrics.scrollHeight, configurable: true });
  }
  if (metrics.clientHeight !== undefined) {
    Object.defineProperty(el, "clientHeight", { value: metrics.clientHeight, configurable: true });
  }
}

afterEach(cleanup);

describe("VirtualList", () => {
  it("renders only a window of the 1000 items", () => {
    renderList();
    const rows = screen.getAllByTestId("vrow");
    // ceil(height 200 / rowHeight 20) + overscan 5 = 15 (lower bound clamps at 0).
    expect(rows.length).toBe(15);
    expect(screen.getByText("row-0")).toBeInTheDocument();
    expect(screen.queryByText("row-500")).toBeNull();
  });

  it("sizes the spacer to items.length * rowHeight", () => {
    const el = renderList();
    const spacer = el.firstElementChild as HTMLElement;
    expect(spacer.style.height).toBe(`${1000 * 20}px`);
  });

  it("moves the window on scroll", () => {
    const el = renderList();
    defineScrollMetrics(el, { scrollTop: 5000, scrollHeight: 20000, clientHeight: 200 });
    fireEvent.scroll(el);
    expect(screen.queryByText("row-0")).toBeNull();
    expect(screen.getByText("row-250")).toBeInTheDocument();
  });

  it("clamps the window at the end of the list", () => {
    const el = renderList();
    defineScrollMetrics(el, { scrollTop: 19800, scrollHeight: 20000, clientHeight: 200 });
    fireEvent.scroll(el);
    expect(screen.getByText("row-999")).toBeInTheDocument();
    const rows = screen.getAllByTestId("vrow");
    expect(rows.length).toBeLessThan(50);
  });

  it("reports scrolling away from the tail and back", () => {
    const onAway = vi.fn();
    const el = renderList({ followTail: true, onScrollAwayFromTail: onAway });
    defineScrollMetrics(el, { scrollHeight: 20000, clientHeight: 200 });

    // Scroll to the middle: away from tail.
    defineScrollMetrics(el, { scrollTop: 5000 });
    fireEvent.scroll(el);
    expect(onAway).toHaveBeenLastCalledWith(true);

    // Scroll back to the bottom (within one rowHeight of the end): at tail.
    defineScrollMetrics(el, { scrollTop: 19800 });
    fireEvent.scroll(el);
    expect(onAway).toHaveBeenLastCalledWith(false);
  });

  it("pins the view to the bottom on new items when followTail and at tail", () => {
    const { rerender } = render(
      <VirtualList<Row>
        items={ITEMS}
        rowHeight={20}
        height={200}
        renderRow={(item) => <span data-testid="vrow">{item.label}</span>}
        followTail
        testId="vlist"
      />,
    );
    const el = screen.getByTestId("vlist");
    // At tail (default on mount); grow the list and expect a scroll-to-bottom.
    defineScrollMetrics(el, { scrollTop: 0, scrollHeight: 20020, clientHeight: 200 });
    rerender(
      <VirtualList<Row>
        items={[...ITEMS, { seq: 1000, label: "row-1000" }]}
        rowHeight={20}
        height={200}
        renderRow={(item) => <span data-testid="vrow">{item.label}</span>}
        followTail
        testId="vlist"
      />,
    );
    expect(el.scrollTop).toBe(20020);
  });

  it("does NOT auto-jump on new items when the user scrolled away", () => {
    const { rerender } = render(
      <VirtualList<Row>
        items={ITEMS}
        rowHeight={20}
        height={200}
        renderRow={(item) => <span data-testid="vrow">{item.label}</span>}
        followTail
        testId="vlist"
      />,
    );
    const el = screen.getByTestId("vlist");
    defineScrollMetrics(el, { scrollTop: 5000, scrollHeight: 20000, clientHeight: 200 });
    fireEvent.scroll(el); // user is now away from the tail
    rerender(
      <VirtualList<Row>
        items={[...ITEMS, { seq: 1000, label: "row-1000" }]}
        rowHeight={20}
        height={200}
        renderRow={(item) => <span data-testid="vrow">{item.label}</span>}
        followTail
        testId="vlist"
      />,
    );
    expect(el.scrollTop).toBe(5000);
  });

  it("uses itemKey for the rendered rows", () => {
    const itemKey = vi.fn((item: Row) => item.seq);
    renderList({ itemKey });
    const rows = screen.getAllByTestId("vrow");
    expect(itemKey).toHaveBeenCalledTimes(rows.length);
    expect(itemKey).toHaveBeenCalledWith(ITEMS[0], 0);
  });
});
