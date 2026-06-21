import { describe, expect, it } from "vitest";

import type { RunEvent } from "../../types/platform";
import { runActionSummary } from "./replayDiff";

describe("runActionSummary", () => {
  it("renders one stable line per tool_call (name + resource)", () => {
    const events: RunEvent[] = [
      { type: "tool_call", data: { name: "read_repo", args: { resource: "acme/x" } } },
      { type: "tool_call", data: { name: "open_pr", args: { resource: "acme/x" } } },
    ];
    expect(runActionSummary(events)).toBe("read_repo acme/x\nopen_pr acme/x");
  });
  it("is empty for no tool_calls", () => {
    expect(runActionSummary([{ type: "agent_start" }])).toBe("");
  });
  it("is defensive: missing name/args/resource degrade to empty fields", () => {
    const events: RunEvent[] = [
      { type: "tool_call", data: { name: "list_repos" } },
      { type: "tool_call", data: {} },
      { type: "tool_call" },
    ];
    expect(runActionSummary(events)).toBe("list_repos\n\n");
  });
  it("ignores non tool_call frames between calls (stable order)", () => {
    const events: RunEvent[] = [
      { type: "agent_start" },
      { type: "tool_call", data: { name: "read_repo", args: { resource: "a" } } },
      { type: "result", data: { actions: [] } },
      { type: "tool_call", data: { name: "merge_pr", args: { resource: "b" } } },
      { type: "agent_end" },
    ];
    expect(runActionSummary(events)).toBe("read_repo a\nmerge_pr b");
  });
});
