import { describe, expect, it } from "vitest";
import { lineDiff } from "./diff";

describe("lineDiff", () => {
  it("marks identical lines as same", () => {
    const rows = lineDiff("a\nb", "a\nb");
    expect(rows.every((r) => r.kind === "same")).toBe(true);
    expect(rows.map((r) => r.left)).toEqual(["a", "b"]);
  });
  it("emits left+right for a changed line", () => {
    const rows = lineDiff("a\nX\nc", "a\nY\nc");
    expect(rows.find((r) => r.kind === "left")?.left).toBe("X");
    expect(rows.find((r) => r.kind === "right")?.right).toBe("Y");
    // unchanged lines still present as same
    expect(rows.filter((r) => r.kind === "same").map((r) => r.left)).toEqual(["a", "c"]);
  });
  it("pads when lengths differ", () => {
    const rows = lineDiff("a", "a\nb");
    expect(rows.some((r) => r.kind === "right" && r.right === "b" && r.left === "")).toBe(true);
  });
});
