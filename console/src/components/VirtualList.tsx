/**
 * VirtualList -- hand-rolled fixed-row-height windowed list (no dependency).
 *
 * Renders only the visible slice of a large list: a scroll container of the
 * given height holds a spacer sized to the full list, and the visible rows
 * are absolutely positioned inside it at index * rowHeight. Purely
 * presentational: no fetching, no timers -- the parent owns the data.
 *
 * followTail: while the user is AT the tail (within one rowHeight of the
 * bottom), growing the list keeps the view pinned to the bottom. Scrolling
 * up reports onScrollAwayFromTail(true) and STOPS the auto-pin (the parent
 * shows a "N new" affordance instead); scrolling back to the tail reports
 * false and resumes pinning. There is never an auto-jump while away.
 *
 * onScrollAwayFromTail should be a stable callback (wrap it in useCallback
 * in the parent): it is a dependency of the internal scroll handler, so a
 * new identity on every parent render re-creates the handler each render.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode, UIEvent } from "react";

export interface VirtualListProps<T> {
  items: readonly T[];
  /** Fixed height of every row, in px. */
  rowHeight: number;
  /** Height of the scroll viewport, in px. */
  height: number;
  renderRow: (item: T, index: number) => ReactNode;
  /** Extra rows rendered above/below the viewport (default 5). */
  overscan?: number;
  /** Keep the view pinned to the bottom while the user is at the tail. */
  followTail?: boolean;
  /** Fired when the user leaves (true) or returns to (false) the tail. */
  onScrollAwayFromTail?: (away: boolean) => void;
  /** Stable row key; defaults to the index. Panels should pass the row seq
   *  so React state survives the window shifting under the rows. */
  itemKey?: (item: T, index: number) => string | number;
  /** Monotonically increasing signal: when it CHANGES (not on mount), the view
   *  scrolls to the bottom and tail pinning is re-armed. Lets a parent offer a
   *  "resume follow" affordance without the list exposing a scroll API. */
  scrollToTailSignal?: number;
  testId?: string;
}

export function VirtualList<T>({
  items,
  rowHeight,
  height,
  renderRow,
  overscan = 5,
  followTail = false,
  onScrollAwayFromTail,
  itemKey,
  scrollToTailSignal,
  testId,
}: VirtualListProps<T>): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  // An empty/just-mounted list counts as "at tail" so the first burst of
  // rows pins to the bottom under followTail.
  const atTailRef = useRef(true);

  const onScroll = useCallback(
    (event: UIEvent<HTMLDivElement>): void => {
      const el = event.currentTarget;
      setScrollTop(el.scrollTop);
      const atTail = el.scrollTop + el.clientHeight >= el.scrollHeight - rowHeight;
      if (atTail !== atTailRef.current) {
        atTailRef.current = atTail;
        onScrollAwayFromTail?.(!atTail);
      }
    },
    [rowHeight, onScrollAwayFromTail],
  );

  // Pin to the bottom when new rows arrive while the user is at the tail.
  // Assigning scrollTop does not fire a scroll event in every environment,
  // so the window state is synced explicitly.
  useEffect(() => {
    if (!followTail || !atTailRef.current) {
      return;
    }
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      setScrollTop(el.scrollTop);
    }
  }, [followTail, items.length]);

  // Forced scroll-to-tail: a CHANGE of the signal (never the mount value)
  // jumps to the bottom and re-arms the tail pin, so followTail resumes.
  const lastTailSignalRef = useRef(scrollToTailSignal);
  useEffect(() => {
    if (scrollToTailSignal === undefined || scrollToTailSignal === lastTailSignalRef.current) {
      return;
    }
    lastTailSignalRef.current = scrollToTailSignal;
    atTailRef.current = true;
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      setScrollTop(el.scrollTop);
    }
  }, [scrollToTailSignal]);

  const first = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const last = Math.min(items.length, Math.ceil((scrollTop + height) / rowHeight) + overscan);
  const visible = items.slice(first, last);

  return (
    <div
      ref={containerRef}
      data-testid={testId}
      onScroll={onScroll}
      style={{ height, overflowY: "auto" }}
    >
      <div style={{ height: items.length * rowHeight, position: "relative" }}>
        {visible.map((item, i) => {
          const index = first + i;
          return (
            <div
              key={itemKey ? itemKey(item, index) : index}
              style={{
                position: "absolute",
                top: index * rowHeight,
                left: 0,
                right: 0,
                height: rowHeight,
              }}
            >
              {renderRow(item, index)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
