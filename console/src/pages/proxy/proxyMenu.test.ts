/**
 * Unit tests for the pure source-menu helpers (deterministic, I4).
 */

import { describe, expect, it } from "vitest";

import { badgeLabel, badgeOutcome, type SourceStatus } from "./proxyMenu";

describe("badgeOutcome", () => {
  it("is idle when no status reported yet", () => {
    expect(badgeOutcome(undefined)).toBe("idle");
  });

  it("is off when the feature is disabled, even with a count", () => {
    const s: SourceStatus = { count: 0, disabled: true };
    expect(badgeOutcome(s)).toBe("off");
  });

  it("is fail when at least one failure is reported", () => {
    expect(badgeOutcome({ count: 5, failed: 2 })).toBe("fail");
  });

  it("is ok for a healthy non-empty view", () => {
    expect(badgeOutcome({ count: 5, failed: 0 })).toBe("ok");
    expect(badgeOutcome({ count: 0 })).toBe("ok");
  });
});

describe("badgeLabel", () => {
  it("is empty when no status reported", () => {
    expect(badgeLabel(undefined)).toBe("");
  });

  it("reads off for a disabled feature", () => {
    expect(badgeLabel({ count: 0, disabled: true })).toBe("off");
  });

  it("shows the plain count when nothing failed", () => {
    expect(badgeLabel({ count: 7 })).toBe("7");
    expect(badgeLabel({ count: 7, failed: 0 })).toBe("7");
  });

  it("shows count and failures when some failed", () => {
    expect(badgeLabel({ count: 7, failed: 3 })).toBe("7 / 3 KO");
  });
});
