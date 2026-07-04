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
