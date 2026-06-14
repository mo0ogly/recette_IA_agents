/**
 * groupSteps -- pure fold of a campaign run's frames into one entry per step.
 * Deterministic: same frames -> same entries. Covers the ordered happy path, a
 * step error, and the declared-plan fallback when no run has streamed yet.
 */

import { describe, expect, it } from "vitest";

import { groupSteps } from "./campaignSteps";
import type { RunEvent } from "../types/platform";

const frames = (list: Array<Record<string, unknown>>): RunEvent[] =>
  list as unknown as RunEvent[];

describe("groupSteps", () => {
  it("folds frames into one entry per step, in order", () => {
    const entries = groupSteps(
      frames([
        { seq: 1, type: "agent_start", data: { index: 0, agent_id: "a", provider: "stub" } },
        {
          seq: 2,
          type: "step",
          data: { index: 0, agent_id: "a", action: { action_type: "open_pr", target_system: "github", resource: "r" } },
        },
        { seq: 3, type: "agent_done", data: { index: 0, agent_id: "a", actions: 1, recording_id: "rec-a" } },
        { seq: 4, type: "agent_start", data: { index: 1, agent_id: "b", provider: "stub" } },
        { seq: 5, type: "step_error", data: { index: 1, agent_id: "b", message: "overreach" } },
      ]),
      [],
    );
    expect(entries.map((e) => e.agentId)).toEqual(["a", "b"]);
    expect(entries[0].status).toBe("done");
    expect(entries[0].actions).toEqual(["open_pr -> github/r"]);
    expect(entries[0].recordingId).toBe("rec-a");
    expect(entries[1].status).toBe("error");
    expect(entries[1].message).toBe("overreach");
  });

  it("is deterministic regardless of frame arrival order (sorts by seq)", () => {
    const list = [
      { seq: 3, type: "agent_done", data: { index: 0, agent_id: "a", actions: 0, recording_id: "rec" } },
      { seq: 1, type: "agent_start", data: { index: 0, agent_id: "a", provider: "stub" } },
      { seq: 2, type: "step", data: { index: 0, agent_id: "a", action: {} } },
    ];
    const a = groupSteps(frames(list), []);
    const b = groupSteps(frames([...list].reverse()), []);
    expect(a).toEqual(b);
    expect(a[0].actions).toEqual(["etape sans action externe"]);
  });

  it("handles a step_error with no preceding agent_start as its own entry", () => {
    const entries = groupSteps(
      frames([{ seq: 1, type: "step_error", data: { index: 0, agent_id: "ghost", message: "unknown agent" } }]),
      [],
    );
    expect(entries).toHaveLength(1);
    expect(entries[0].agentId).toBe("ghost");
    expect(entries[0].status).toBe("error");
  });

  it("falls back to the declared plan when there are no frames", () => {
    const entries = groupSteps([], [{ agent_id: "a" }, { agent_id: "b" }]);
    expect(entries.map((e) => e.agentId)).toEqual(["a", "b"]);
    expect(entries.every((e) => e.status === "pending")).toBe(true);
  });
});
