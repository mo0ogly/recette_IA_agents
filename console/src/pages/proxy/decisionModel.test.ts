import { describe, expect, it } from "vitest";
import type { RunEvent } from "../../types/platform";
import { decisionForIndex, decisionsFromEvents } from "./decisionModel";

describe("decisionsFromEvents", () => {
  it("extracts ordered tool_call decisions with the tool name", () => {
    const events: RunEvent[] = [
      { type: "agent_start", agent_id: "a" },
      { type: "step", index: 0, text: "I will read the repo" },
      { type: "tool_call", tool_name: "read_repo", tool_args: { resource: "acme/x" } },
      { type: "step", index: 1, text: "now open a PR" },
      { type: "tool_call", tool_name: "open_pr", tool_args: { resource: "acme/x" } },
      { type: "result", data: { actions: [] } },
    ];
    const d = decisionsFromEvents(events);
    expect(d.map((x) => x.toolName)).toEqual(["read_repo", "open_pr"]);
    expect(d[0].index).toBe(0);
    expect(d[0].summary).toContain("read_repo");
  });
  it("returns [] when there are no tool_call frames", () => {
    expect(decisionsFromEvents([{ type: "result", data: {} }])).toEqual([]);
  });
  it("reads the real wire shape (data.name) emitted by /runs/{id}/events", () => {
    const events: RunEvent[] = [
      { seq: 1, type: "step", data: { index: 0, decision: { text: "read first" } } },
      {
        seq: 2,
        type: "tool_call",
        data: { index: 0, name: "read_repo", args: { resource: "acme/x" } },
      },
      {
        seq: 3,
        type: "tool_call",
        data: { index: 1, name: "open_pr", args: { resource: "acme/x" } },
      },
    ];
    const d = decisionsFromEvents(events);
    expect(d.map((x) => x.toolName)).toEqual(["read_repo", "open_pr"]);
  });
});

describe("decisionForIndex", () => {
  it("maps exchange index to its decision, undefined out of range", () => {
    const d = decisionsFromEvents([
      { type: "tool_call", tool_name: "read_repo" },
      { type: "tool_call", tool_name: "open_pr" },
    ]);
    expect(decisionForIndex(d, 1)?.toolName).toBe("open_pr");
    expect(decisionForIndex(d, 5)).toBeUndefined();
  });
});
