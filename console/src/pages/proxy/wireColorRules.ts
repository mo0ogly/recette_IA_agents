/**
 * wireColorRules — Wireshark-style coloring rules over captured agent flows.
 *
 * A coloring rule pairs a display-filter predicate (wireFilter DSL) with a
 * named tint; the FIRST matching rule colors the row (Wireshark semantics).
 * Rules are serialized into one URL query param so a colored view is
 * deep-linkable and shareable, like a Wireshark profile.
 *
 * Pure and deterministic (I4): parsing, compiling and matching are functions
 * of the rules string and the flow only — no clock, no I/O, stable order.
 *
 * Wire format (the `colors` query param):
 *   "<tint>:<display-filter>;<tint>:<display-filter>;..."
 * e.g. "red:status >= 500;amber:l8.tool == \"delete_repo\""
 * The tint is one of the theme badge tokens; the filter is any valid
 * wireFilter expression. Semicolons inside quoted strings are preserved.
 */

import type { WireFlow } from "../../types/platform";
import { compileWireFilter } from "./wireFilter";

/** Allowed tints — each maps to an existing badge token pair in CSS. */
export const COLOR_TINTS = ["red", "amber", "green", "gray", "orange"] as const;
export type ColorTint = (typeof COLOR_TINTS)[number];

export interface ColorRule {
  tint: ColorTint;
  filter: string;
}

export interface ColorRuleError {
  /** 0-based index of the offending rule in the parsed list. */
  index: number;
  error: string;
}

export interface CompiledColorRules {
  rules: ColorRule[];
  errors: ColorRuleError[];
  /** First-matching-rule tint for a flow, or null (no rule matched). */
  tintFor: (flow: WireFlow) => ColorTint | null;
}

function _isTint(v: string): v is ColorTint {
  return (COLOR_TINTS as readonly string[]).includes(v);
}

/** Split on ";" but keep semicolons inside double-quoted strings. */
function _splitRules(src: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inString = false;
  for (const c of src) {
    if (c === '"') inString = !inString;
    if (c === ";" && !inString) {
      out.push(cur);
      cur = "";
    } else {
      cur += c;
    }
  }
  out.push(cur);
  return out.map((s) => s.trim()).filter((s) => s.length > 0);
}

/** Parse the wire format into rules; malformed entries are dropped with an error. */
export function parseColorRules(src: string): { rules: ColorRule[]; errors: ColorRuleError[] } {
  const rules: ColorRule[] = [];
  const errors: ColorRuleError[] = [];
  _splitRules(src).forEach((entry, index) => {
    const sep = entry.indexOf(":");
    if (sep === -1) {
      errors.push({ index, error: `rule "${entry}" is missing the "tint:filter" separator` });
      return;
    }
    const tint = entry.slice(0, sep).trim().toLowerCase();
    const filter = entry.slice(sep + 1).trim();
    if (!_isTint(tint)) {
      errors.push({ index, error: `unknown tint "${tint}" (allowed: ${COLOR_TINTS.join(", ")})` });
      return;
    }
    if (filter.length === 0) {
      errors.push({ index, error: `rule ${index + 1} has an empty filter` });
      return;
    }
    rules.push({ tint, filter });
  });
  return { rules, errors };
}

/** Serialize rules back to the wire format (inverse of parseColorRules). */
export function serializeColorRules(rules: ColorRule[]): string {
  return rules.map((r) => `${r.tint}:${r.filter}`).join(";");
}

/** Compile the rules string into a first-match tint function. A rule whose
 *  filter fails to compile is surfaced as an error and never matches (the
 *  view stays usable, like the display-filter's pass-through on error). */
export function compileColorRules(src: string): CompiledColorRules {
  const { rules, errors } = parseColorRules(src);
  const compiled = rules.map((rule, index) => {
    const c = compileWireFilter(rule.filter);
    if (!c.ok && c.error !== null) {
      errors.push({ index, error: c.error });
      return { tint: rule.tint, predicate: null as ((f: WireFlow) => boolean) | null };
    }
    return { tint: rule.tint, predicate: c.predicate };
  });
  const active = compiled.filter(
    (c): c is { tint: ColorTint; predicate: (f: WireFlow) => boolean } => c.predicate !== null,
  );
  return {
    rules,
    errors,
    tintFor: (flow: WireFlow): ColorTint | null => {
      for (const c of active) {
        if (c.predicate(flow)) return c.tint;
      }
      return null;
    },
  };
}
