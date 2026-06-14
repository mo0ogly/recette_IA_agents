import { describe, expect, it } from "vitest";
import { launchTally, voyantFor } from "./runStatus";

describe("launchTally", () => {
  it("counts completed/failed/stopped, ignoring pending and running", () => {
    const runs = [
      { status: "completed" },
      { status: "completed" },
      { status: "failed" },
      { status: "stopped" },
      { status: "running" },
      { status: "pending" },
    ];
    expect(launchTally(runs)).toEqual({ succeeded: 2, failed: 1, stopped: 1 });
  });

  it("is all-zero on an empty list", () => {
    expect(launchTally([])).toEqual({ succeeded: 0, failed: 0, stopped: 0 });
  });

  it("ignores unknown statuses", () => {
    expect(launchTally([{ status: "weird" }])).toEqual({
      succeeded: 0,
      failed: 0,
      stopped: 0,
    });
  });
});

describe("voyantFor", () => {
  it("maps failed to an error voyant", () => {
    expect(voyantFor("failed").cls).toBe("voyant-error");
  });

  it("falls back to idle on an unknown status", () => {
    expect(voyantFor("").cls).toBe("voyant-idle");
  });
});
