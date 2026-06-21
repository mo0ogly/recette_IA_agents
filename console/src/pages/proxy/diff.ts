/**
 * diff -- pure line-aligned diff for the wire-flow side-by-side compare.
 *
 * Zips two texts by line index: equal lines yield one `same` row, differing
 * lines yield a `left` row (only the A side) plus a `right` row (only the B
 * side), and the shorter side is padded with empty rows. Pure (I4): no clock,
 * no random, no DOM -- a deterministic function of its two inputs, unit-testable
 * without a render.
 */

export interface DiffRow {
  kind: "same" | "left" | "right";
  left: string;
  right: string;
}

/** Line-aligned diff of two texts (see module doc). */
export function lineDiff(a: string, b: string): DiffRow[] {
  const la = a.split("\n");
  const lb = b.split("\n");
  const n = Math.max(la.length, lb.length);
  const rows: DiffRow[] = [];
  for (let i = 0; i < n; i++) {
    const l = la[i] ?? "";
    const r = lb[i] ?? "";
    if (i < la.length && i < lb.length && l === r) {
      rows.push({ kind: "same", left: l, right: r });
    } else {
      if (i < la.length) rows.push({ kind: "left", left: l, right: "" });
      if (i < lb.length) rows.push({ kind: "right", left: "", right: r });
    }
  }
  return rows;
}
