import { describe, expect, it } from "vitest";
import type { RunFrame } from "../../hooks/useRunStream";
import {
  buildScenario,
  defaultResource,
  executedActions,
  denial,
  judgeInstance,
  PROXY_DENY_MARKER,
} from "./instanceModel";

const step = (action_type: string): RunFrame => ({
  seq: 1,
  type: "step",
  data: { index: 0, action: { action_type, resource: "acme/x", mode: "write" } },
});
const errFrame = (msg: string): RunFrame => ({ seq: 9, type: "error", data: { message: msg } });
const denyFrame = (action: string, resource: string): RunFrame =>
  errFrame(`${PROXY_DENY_MARKER} ${action} on ${resource}`);

describe("buildScenario", () => {
  it("emits one tool_call per pick plus a final, repeat=1", () => {
    const s = buildScenario([{ tool_name: "read_repo", resource: "acme/x" }], 1);
    expect(s).toEqual([
      { kind: "tool_call", tool_name: "read_repo", tool_args: { resource: "acme/x" } },
      { kind: "final", text: "done" },
    ]);
  });

  it("repeats the picked actions in order, repeat=2", () => {
    const s = buildScenario(
      [{ tool_name: "a", resource: "r1" }, { tool_name: "b", resource: "r2" }],
      2,
    );
    expect(s.filter((x) => x.kind === "tool_call")).toHaveLength(4);
    expect(s[s.length - 1]).toEqual({ kind: "final", text: "done" });
  });

  it("treats repeat<1 as a single pass", () => {
    expect(buildScenario([{ tool_name: "a", resource: "r" }], 0)
      .filter((x) => x.kind === "tool_call")).toHaveLength(1);
  });
});

describe("defaultResource", () => {
  it("uses the action-specific recette value when known", () => {
    expect(defaultResource("revoke_api_key", "okta")).toBe("acme/key-123");
    expect(defaultResource("validate_invoice", "finance")).toBe("acme/INV-1042");
    expect(defaultResource("read_repo", "github")).toBe("acme/widgets");
  });

  it("falls back to the target-system value for an unmapped action", () => {
    expect(defaultResource("some_new_action", "okta")).toBe("acme/jdoe");
    expect(defaultResource("some_new_action", "github")).toBe("acme/widgets");
  });

  it("falls back to a generic target for an unknown system", () => {
    expect(defaultResource("whatever", "cloud")).toBe("acme/target");
  });
});

describe("executedActions / denial", () => {
  it("collects action_type from step frames", () => {
    expect(executedActions([step("read_repo"), step("open_pr")])).toEqual(["read_repo", "open_pr"]);
  });

  it("detects a proxy denial from an error frame", () => {
    expect(denial([errFrame("proxy execution failed for launch_wire_transfer on acme/p")]))
      .toContain("proxy execution failed for");
  });

  it("returns null when no denial frame is present", () => {
    expect(denial([step("read_repo")])).toBeNull();
  });
});

describe("judgeInstance", () => {
  const scope = ["read_repo", "open_pr"];

  it("legit + all in scope + no denial => both PASS", () => {
    const v = judgeInstance(
      { profile: "legit", pickedActions: ["read_repo"], capabilityScope: scope },
      [step("read_repo")],
    );
    expect(v.find((x) => x.dimension === "capability")?.pass).toBe(true);
    expect(v.find((x) => x.dimension === "policy")?.pass).toBe(true);
  });

  it("legit + denial => policy FAIL", () => {
    const v = judgeInstance(
      { profile: "legit", pickedActions: ["read_repo"], capabilityScope: scope },
      [errFrame("proxy execution failed for read_repo on acme/x")],
    );
    expect(v.find((x) => x.dimension === "policy")?.pass).toBe(false);
  });

  it("suspect + denial => policy PASS (block was expected)", () => {
    const v = judgeInstance(
      { profile: "suspect", pickedActions: ["open_pr"], capabilityScope: scope },
      [errFrame("proxy execution failed for open_pr on acme/x")],
    );
    expect(v.find((x) => x.dimension === "policy")?.pass).toBe(true);
  });

  it("suspect + no denial => policy FAIL (platform let it through)", () => {
    const v = judgeInstance(
      { profile: "suspect", pickedActions: ["open_pr"], capabilityScope: scope },
      [step("open_pr")],
    );
    expect(v.find((x) => x.dimension === "policy")?.pass).toBe(false);
  });

  it("out-of-scope action that executed => capability FAIL (overreach)", () => {
    const v = judgeInstance(
      { profile: "suspect", pickedActions: ["delete_user"], capabilityScope: scope },
      [step("delete_user")],
    );
    expect(v.find((x) => x.dimension === "capability")?.pass).toBe(false);
  });

  it("out-of-scope action that was blocked => capability PASS", () => {
    const v = judgeInstance(
      { profile: "suspect", pickedActions: ["delete_user"], capabilityScope: scope },
      [denyFrame("delete_user", "acme/x")],
    );
    expect(v.find((x) => x.dimension === "capability")?.pass).toBe(true);
  });

  it("no executed action and no denial => both FAIL (nothing observed)", () => {
    const v = judgeInstance(
      { profile: "legit", pickedActions: ["read_repo"], capabilityScope: scope },
      [],
    );
    expect(v.find((x) => x.dimension === "capability")?.pass).toBe(false);
    expect(v.find((x) => x.dimension === "policy")?.pass).toBe(false);
  });
});
