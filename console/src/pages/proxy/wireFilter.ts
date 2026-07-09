/**
 * wireFilter — a Wireshark-style display-filter DSL over dissected agent flows.
 *
 * Grammar (composable, case-insensitive keywords):
 *   expr    := or
 *   or      := and ( "||" and )*
 *   and     := not ( "&&" not )*
 *   not     := "!" not | primary
 *   primary := "(" expr ")" | comparison | field         (bare field = "present")
 *   comparison := field OP value
 *   OP      := == | != | >= | <= | > | < | contains | ~ (regex)
 *   value   := "quoted" | number | bareword
 *
 * Fields resolve through wireFields.ts (l3l4/tls/http/timing/l8 + host/method/
 * status/session/instance). A repeated field (l8.tool) matches when ANY element
 * matches. Pure and deterministic (I4): compiling a filter yields a pure
 * predicate `(flow) => boolean`; no I/O, no clock. A parse error is reported,
 * never thrown into the render path.
 */

import type { WireFlow } from "../../types/platform";
import { WIRE_FIELDS, type FieldValue, type WireField } from "./wireFields";

type Op = "==" | "!=" | ">=" | "<=" | ">" | "<" | "contains" | "~";
const _OPS: Op[] = ["==", "!=", ">=", "<=", ">", "<", "contains", "~"];

type Token =
  | { kind: "op"; value: Op }
  | { kind: "and" }
  | { kind: "or" }
  | { kind: "not" }
  | { kind: "lparen" }
  | { kind: "rparen" }
  | { kind: "word"; value: string }
  | { kind: "string"; value: string };

export interface CompileResult {
  ok: boolean;
  predicate: (flow: WireFlow) => boolean;
  error: string | null;
}

const _ALWAYS: (flow: WireFlow) => boolean = () => true;

function tokenize(src: string): Token[] {
  const out: Token[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === " " || c === "\t" || c === "\n") {
      i += 1;
      continue;
    }
    if (c === "(") {
      out.push({ kind: "lparen" });
      i += 1;
      continue;
    }
    if (c === ")") {
      out.push({ kind: "rparen" });
      i += 1;
      continue;
    }
    if (c === "&" && src[i + 1] === "&") {
      out.push({ kind: "and" });
      i += 2;
      continue;
    }
    if (c === "|" && src[i + 1] === "|") {
      out.push({ kind: "or" });
      i += 2;
      continue;
    }
    if (c === '"' || c === "'") {
      let j = i + 1;
      let value = "";
      while (j < src.length && src[j] !== c) {
        if (src[j] === "\\" && j + 1 < src.length) {
          value += src[j + 1];
          j += 2;
        } else {
          value += src[j];
          j += 1;
        }
      }
      out.push({ kind: "string", value });
      i = j + 1;
      continue;
    }
    // '!' is NOT unless it is part of '!='
    if (c === "!" && src[i + 1] !== "=") {
      out.push({ kind: "not" });
      i += 1;
      continue;
    }
    const two = src.slice(i, i + 2);
    if ((_OPS as string[]).includes(two)) {
      out.push({ kind: "op", value: two as Op });
      i += 2;
      continue;
    }
    if (c === ">" || c === "<" || c === "~") {
      out.push({ kind: "op", value: c as Op });
      i += 1;
      continue;
    }
    // bareword: field path or value (letters, digits, . _ - : / and %)
    let j = i;
    let word = "";
    while (j < src.length && /[A-Za-z0-9._:/%-]/.test(src[j])) {
      word += src[j];
      j += 1;
    }
    if (word === "") {
      // Unknown char: skip it (lenient tokenizer, never throws).
      i += 1;
      continue;
    }
    if (word.toLowerCase() === "contains") {
      out.push({ kind: "op", value: "contains" });
    } else {
      out.push({ kind: "word", value: word });
    }
    i = j;
  }
  return out;
}

type Node = (flow: WireFlow) => boolean;

class Parser {
  private pos = 0;
  constructor(private readonly toks: Token[]) {}

  parse(): Node {
    const node = this.parseOr();
    if (this.pos < this.toks.length) {
      throw new Error(`unexpected token at position ${this.pos}`);
    }
    return node;
  }

  private peek(): Token | undefined {
    return this.toks[this.pos];
  }

  private parseOr(): Node {
    let left = this.parseAnd();
    while (this.peek()?.kind === "or") {
      this.pos += 1;
      const right = this.parseAnd();
      const l = left;
      left = (flow) => l(flow) || right(flow);
    }
    return left;
  }

  private parseAnd(): Node {
    let left = this.parseNot();
    while (this.peek()?.kind === "and") {
      this.pos += 1;
      const right = this.parseNot();
      const l = left;
      left = (flow) => l(flow) && right(flow);
    }
    return left;
  }

  private parseNot(): Node {
    if (this.peek()?.kind === "not") {
      this.pos += 1;
      const inner = this.parseNot();
      return (flow) => !inner(flow);
    }
    return this.parsePrimary();
  }

  private parsePrimary(): Node {
    const tok = this.peek();
    if (tok === undefined) throw new Error("unexpected end of filter");
    if (tok.kind === "lparen") {
      this.pos += 1;
      const inner = this.parseOr();
      if (this.peek()?.kind !== "rparen") throw new Error("missing )");
      this.pos += 1;
      return inner;
    }
    if (tok.kind !== "word") throw new Error("expected a field");
    const field = WIRE_FIELDS[tok.value];
    if (field === undefined) throw new Error(`unknown field: ${tok.value}`);
    this.pos += 1;
    const next = this.peek();
    if (next === undefined || next.kind !== "op") {
      // Bare field = "present" (non-null, non-empty).
      return (flow) => _present(field.get(flow));
    }
    this.pos += 1;
    const valTok = this.peek();
    if (valTok === undefined || (valTok.kind !== "word" && valTok.kind !== "string")) {
      throw new Error(`expected a value after ${next.value}`);
    }
    this.pos += 1;
    return _comparison(field, next.value, valTok.value);
  }
}

function _present(v: FieldValue | FieldValue[]): boolean {
  if (Array.isArray(v)) return v.some((x) => x !== null && x !== "");
  return v !== null && v !== "";
}

function _asList(v: FieldValue | FieldValue[]): FieldValue[] {
  return Array.isArray(v) ? v : [v];
}

function _cmpOne(field: WireField, op: Op, raw: string, actual: FieldValue): boolean {
  if (actual === null) return false;
  if (op === "~") {
    try {
      return new RegExp(raw, "i").test(String(actual));
    } catch {
      return false;
    }
  }
  if (op === "contains") {
    return String(actual).toLowerCase().includes(raw.toLowerCase());
  }
  if (field.type === "number") {
    const a = typeof actual === "number" ? actual : Number(actual);
    const b = Number(raw);
    if (Number.isNaN(a) || Number.isNaN(b)) return op === "!=";
    switch (op) {
      case "==": return a === b;
      case "!=": return a !== b;
      case ">": return a > b;
      case "<": return a < b;
      case ">=": return a >= b;
      case "<=": return a <= b;
    }
  }
  const a = String(actual).toLowerCase();
  const b = raw.toLowerCase();
  switch (op) {
    case "==": return a === b;
    case "!=": return a !== b;
    case ">": return a > b;
    case "<": return a < b;
    case ">=": return a >= b;
    case "<=": return a <= b;
    default: return false;
  }
}

function _comparison(field: WireField, op: Op, raw: string): Node {
  return (flow) => {
    const values = _asList(field.get(flow));
    // A repeated field (l8.tool) matches when ANY element matches; for "!=" the
    // intent is "no element equals", so negate the ANY-equals over the list.
    if (op === "!=") {
      return !values.some((v) => v !== null && _cmpOne(field, "==", raw, v));
    }
    return values.some((v) => _cmpOne(field, op, raw, v));
  };
}

/** Compile a display-filter string into a pure predicate. An empty filter passes
 *  everything; a parse error yields ``ok:false`` with a message and a
 *  pass-through predicate (the caller shows the error, the list stays usable). */
export function compileWireFilter(src: string): CompileResult {
  const trimmed = src.trim();
  if (trimmed === "") return { ok: true, predicate: _ALWAYS, error: null };
  try {
    const predicate = new Parser(tokenize(trimmed)).parse();
    return { ok: true, predicate, error: null };
  } catch (e) {
    return { ok: false, predicate: _ALWAYS, error: e instanceof Error ? e.message : String(e) };
  }
}

/** Apply a compiled filter to a flow list (convenience for the panel). */
export function applyWireFilter(flows: WireFlow[], src: string): WireFlow[] {
  const { predicate } = compileWireFilter(src);
  return flows.filter(predicate);
}
