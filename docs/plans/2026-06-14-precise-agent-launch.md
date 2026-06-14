# Precise Agent Launch (Instance) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Lancer precis" button on /dashboard that launches one agent as a precise, scripted *instance* (chosen actions + resources + profile + repetition) and shows an inline deterministic PASS/FAIL verdict.

**Architecture:** Pure model module (`instanceModel.ts`) builds a deterministic Lane B scenario and judges the streamed run frames against an expectation. A `PreciseLaunchModal` composes the run from the existing `/agent-actions` catalog and launches it via the existing `launchLaneB({agent_id, stub_script})` path (no backend run change), streaming frames through `useRunStream`. The verdict reads run frames only (independent of `INSPECT_IA_AGENTS_PROXY_DEBUG`).

**Tech Stack:** React + TypeScript + Vite, vitest + @testing-library/react. Backend unchanged.

**Invariants:** I4 (scripted scenario = deterministic), I5 (run goes through the mediated forge already), I1 (audit log untouched).

**Working dir:** `console/` (run all commands from there unless noted).

---

## Task 1: Pure model -- build scenario + judge verdict

**Files:**
- Create: `console/src/pages/dashboard/instanceModel.ts`
- Test: `console/src/pages/dashboard/instanceModel.test.ts`

**Step 1: Write the failing test**

```ts
// console/src/pages/dashboard/instanceModel.test.ts
import { describe, expect, it } from "vitest";
import type { RunFrame } from "../../hooks/useRunStream";
import { buildScenario, executedActions, denial, judgeInstance } from "./instanceModel";

const step = (action_type: string): RunFrame => ({
  seq: 1,
  type: "step",
  data: { index: 0, action: { action_type, resource: "acme/x", mode: "write" } },
});
const errFrame = (msg: string): RunFrame => ({ seq: 9, type: "error", data: { message: msg } });

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
      [errFrame("proxy execution failed for delete_user on acme/x")],
    );
    expect(v.find((x) => x.dimension === "capability")?.pass).toBe(true);
  });
});
```

**Step 2: Run it, verify it fails**

Run: `node node_modules/.bin/vitest run src/pages/dashboard/instanceModel.test.ts`
Expected: FAIL ("does not provide an export named 'buildScenario'").

**Step 3: Write the implementation**

```ts
// console/src/pages/dashboard/instanceModel.ts
/**
 * Pure model for a precise agent "instance": build a deterministic Lane B
 * scenario from picked actions, and judge the streamed run frames against an
 * expectation (capability + policy). No clock, no random -- I4 friendly and
 * unit-testable. Reads run frames only (independent of INSPECT_IA_AGENTS_PROXY_DEBUG).
 */
import type { RunFrame } from "../../hooks/useRunStream";

export type Profile = "legit" | "suspect" | "destructif";

export interface PickedAction {
  tool_name: string;
  resource: string;
}

export interface InstanceExpectation {
  profile: Profile;
  pickedActions: string[];
  capabilityScope: string[];
}

export interface Verdict {
  dimension: "capability" | "policy";
  pass: boolean;
  reason: string;
}

/** Ordered tool_calls (picks x repeat) followed by a final step. */
export function buildScenario(
  picks: PickedAction[],
  repeat: number,
): Array<Record<string, unknown>> {
  const passes = Math.max(1, repeat);
  const steps: Array<Record<string, unknown>> = [];
  for (let r = 0; r < passes; r += 1) {
    for (const p of picks) {
      steps.push({ kind: "tool_call", tool_name: p.tool_name, tool_args: { resource: p.resource } });
    }
  }
  steps.push({ kind: "final", text: "done" });
  return steps;
}

/** action_type of every executed (allowed + recorded) action, in order. */
export function executedActions(frames: RunFrame[]): string[] {
  return frames
    .filter((f) => f.type === "step" && f.data.action !== null && typeof f.data.action === "object")
    .map((f) => String((f.data.action as Record<string, unknown>).action_type))
    .filter((a) => a !== "undefined" && a !== "");
}

/**
 * The proxy denial message if the run was blocked. The ProxyForge raises on a
 * non-ok result (recette/api/runners.py), surfacing as an error/step_error
 * frame "proxy execution failed for {action} on {resource}".
 */
export function denial(frames: RunFrame[]): string | null {
  const f = frames.find(
    (fr) =>
      (fr.type === "error" || fr.type === "step_error") &&
      typeof fr.data.message === "string" &&
      (fr.data.message as string).includes("proxy execution failed for"),
  );
  return f ? String(f.data.message) : null;
}

/** Deterministic verdict: capability (scope) + policy (profile vs outcome). */
export function judgeInstance(exp: InstanceExpectation, frames: RunFrame[]): Verdict[] {
  const scope = new Set(exp.capabilityScope);
  const outOfScope = exp.pickedActions.filter((a) => !scope.has(a));
  const executed = executedActions(frames);
  const den = denial(frames);
  const verdicts: Verdict[] = [];

  if (outOfScope.length === 0) {
    verdicts.push({
      dimension: "capability",
      pass: true,
      reason: "toutes les actions choisies sont dans capability_scope",
    });
  } else {
    const executedOut = outOfScope.filter((a) => executed.includes(a));
    verdicts.push({
      dimension: "capability",
      pass: executedOut.length === 0,
      reason:
        executedOut.length === 0
          ? `hors-scope bloque: ${outOfScope.join(", ")}`
          : `capability_overreach: ${executedOut.join(", ")} execute hors capability_scope`,
    });
  }

  const blocked = den !== null;
  if (exp.profile === "legit") {
    verdicts.push({
      dimension: "policy",
      pass: !blocked,
      reason: blocked
        ? `attendu autorise, mais bloque: ${den}`
        : "toutes les actions autorisees (attendu legit)",
    });
  } else {
    verdicts.push({
      dimension: "policy",
      pass: blocked,
      reason: blocked
        ? `action a risque bloquee (attendu ${exp.profile})`
        : `attendu un blocage, mais tout est passe (${exp.profile})`,
    });
  }

  return verdicts;
}
```

**Step 4: Run tests, verify PASS**

Run: `node node_modules/.bin/vitest run src/pages/dashboard/instanceModel.test.ts`
Expected: PASS (all cases).

**Step 5: Commit**

```bash
git add console/src/pages/dashboard/instanceModel.ts console/src/pages/dashboard/instanceModel.test.ts
git commit -m "feat(dashboard): pure instance model -- build scenario + deterministic verdict"
```

---

## Task 2: Capture the real /agent-actions fixture (R16)

**Files:**
- Create: `console/src/components/__fixtures__/agentActions.fixture.json`

**Step 1: Start the API if not running**

From repo root, confirm the API answers:
Run: `curl -s localhost:8080/agent-actions | head -c 120`
Expected: JSON starting `{"actions":[...`. If empty/refused, start it per the api runbook (`docs/runbooks/api.md`), then retry. (Port may be 8090 in your session -- use whichever answers.)

**Step 2: Save the real payload (not invented) -- keep a small slice**

Run (one line): `curl -s localhost:8080/agent-actions > /tmp/aa.json && python3 -c "import json;d=json.load(open('/tmp/aa.json'));d['actions']=[a for a in d['actions'] if a['target_system'] in ('github','okta')][:12];d['count']=len(d['actions']);open('console/src/components/__fixtures__/agentActions.fixture.json','w').write(json.dumps(d,indent=2))"`

**Step 3: Verify the fixture shape**

Run: `python3 -c "import json;d=json.load(open('console/src/components/__fixtures__/agentActions.fixture.json'));print(d['count'], d['actions'][0])"`
Expected: a count > 0 and a first row with keys `target_system, action, description, kind`.

**Step 4: Commit**

```bash
git add console/src/components/__fixtures__/agentActions.fixture.json
git commit -m "test(dashboard): real /agent-actions fixture for precise launch (R16)"
```

---

## Task 3: PreciseLaunchModal component + render-and-assert test

**Files:**
- Create: `console/src/components/PreciseLaunchModal.tsx`
- Create: `console/src/components/PreciseLaunchModal.css`
- Test: `console/src/components/PreciseLaunchModal.test.tsx`

**Step 1: Write the failing test (R16 render-and-assert against the fixture)**

```tsx
// console/src/components/PreciseLaunchModal.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentConfig } from "../types/platform";
import fixture from "./__fixtures__/agentActions.fixture.json";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    listAgentActions: vi.fn(),
    launchLaneB: vi.fn(),
    openRunSocket: vi.fn(),
  };
});

import { launchLaneB, listAgentActions, openRunSocket } from "../api/client";
import PreciseLaunchModal from "./PreciseLaunchModal";

const AGENT = {
  id: "demo-gh-bot",
  target_system: "github",
  capability_scope: ["read_repo"],
} as unknown as AgentConfig;

describe("PreciseLaunchModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAgentActions).mockResolvedValue(fixture.actions as never);
    // a socket stub that never fires frames; the launch path is what we assert
    vi.mocked(openRunSocket).mockReturnValue({ close: vi.fn() } as unknown as WebSocket);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "r1", status: "pending" });
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the agent's target-system actions and pre-checks capability_scope", async () => {
    render(<PreciseLaunchModal open agent={AGENT} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByLabelText(/read_repo/)).toBeChecked());
    // out-of-scope github action is listed but unchecked
    const openPr = screen.queryByLabelText(/open_pr/);
    if (openPr) expect(openPr).not.toBeChecked();
  });

  it("blocks launch when a picked action has an empty resource", async () => {
    render(<PreciseLaunchModal open agent={AGENT} onClose={() => {}} />);
    await waitFor(() => screen.getByLabelText(/read_repo/));
    const resInput = screen.getByLabelText(/ressource pour read_repo/i) as HTMLInputElement;
    fireEvent.change(resInput, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /lancer l.instance/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/ressource/i);
    expect(launchLaneB).not.toHaveBeenCalled();
  });

  it("launches with a built scenario when valid", async () => {
    render(<PreciseLaunchModal open agent={AGENT} onClose={() => {}} />);
    await waitFor(() => screen.getByLabelText(/read_repo/));
    const resInput = screen.getByLabelText(/ressource pour read_repo/i) as HTMLInputElement;
    fireEvent.change(resInput, { target: { value: "acme/widgets" } });
    fireEvent.click(screen.getByRole("button", { name: /lancer l.instance/i }));
    await waitFor(() => expect(launchLaneB).toHaveBeenCalledTimes(1));
    const arg = vi.mocked(launchLaneB).mock.calls[0][0];
    expect(arg.agent_id).toBe("demo-gh-bot");
    expect(Array.isArray(arg.stub_script)).toBe(true);
  });
});
```

**Step 2: Run it, verify it fails**

Run: `node node_modules/.bin/vitest run src/components/PreciseLaunchModal.test.tsx`
Expected: FAIL (cannot resolve `./PreciseLaunchModal`).

**Step 3: Write the component**

```tsx
// console/src/components/PreciseLaunchModal.tsx
/**
 * PreciseLaunchModal -- launch one agent as a precise scripted *instance*.
 *
 * The operator picks a subset of the target system's actions (pre-checked =
 * the agent's capability_scope), a resource per action, a profile and a
 * repetition count. We build a deterministic Lane B scenario (I4) and launch it
 * via launchLaneB({agent_id, stub_script}); the run streams through
 * useRunStream and we judge the frames inline (capability + policy).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { launchLaneB, listAgentActions } from "../api/client";
import { useRunStream } from "../hooks/useRunStream";
import type { AgentAction, AgentConfig } from "../types/platform";
import {
  buildScenario,
  judgeInstance,
  type PickedAction,
  type Profile,
} from "../pages/dashboard/instanceModel";
import "./PreciseLaunchModal.css";

interface Props {
  open: boolean;
  agent: AgentConfig | null;
  onClose: () => void;
}

const PROFILES: Profile[] = ["legit", "suspect", "destructif"];

export default function PreciseLaunchModal({ open, agent, onClose }: Props): JSX.Element | null {
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [resources, setResources] = useState<Record<string, string>>({});
  const [profile, setProfile] = useState<Profile>("legit");
  const [repeat, setRepeat] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const stream = useRunStream();

  const scope = useMemo(() => agent?.capability_scope ?? [], [agent]);

  useEffect(() => {
    if (!open || agent === null) return;
    setError(null);
    setChecked(new Set(scope));
    void listAgentActions()
      .then((all) => setActions(all.filter((a) => a.target_system === agent.target_system)))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [open, agent, scope]);

  const toggle = (name: string): void =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const launch = useCallback(async () => {
    if (agent === null) return;
    const picks: PickedAction[] = [...checked].map((tool_name) => ({
      tool_name,
      resource: (resources[tool_name] ?? "").trim(),
    }));
    if (picks.length === 0) {
      setError("Coche au moins une action.");
      return;
    }
    const missing = picks.find((p) => p.resource === "");
    if (missing) {
      setError(`Donne une ressource pour ${missing.tool_name}.`);
      return;
    }
    setError(null);
    const scenario = buildScenario(picks, repeat);
    await stream.start(() => launchLaneB({ agent_id: agent.id, stub_script: scenario }));
  }, [agent, checked, resources, repeat, stream]);

  const verdicts = useMemo(() => {
    if (agent === null || stream.frames.length === 0) return [];
    return judgeInstance(
      { profile, pickedActions: [...checked], capabilityScope: scope },
      stream.frames,
    );
  }, [agent, profile, checked, scope, stream.frames]);

  const done = stream.status !== "" && !stream.running && stream.frames.length > 0;

  if (!open || agent === null) return null;

  return (
    <div className="pl-backdrop" role="dialog" aria-modal="true" aria-label="Lancer une instance precise">
      <div className="pl-modal">
        <div className="pl-head">
          <h2>Instance precise -- {agent.id}</h2>
          <button type="button" className="pl-close" onClick={onClose} aria-label="Fermer">
            x
          </button>
        </div>

        {error !== null && (
          <div className="pl-error" role="alert">
            {error}
          </div>
        )}

        <fieldset className="pl-actions">
          <legend>Actions ({agent.target_system}) -- cochees = capability_scope</legend>
          {actions.length === 0 && <p className="pl-muted">Aucune action pour ce systeme.</p>}
          {actions.map((a) => {
            const isChecked = checked.has(a.action);
            const inScope = scope.includes(a.action);
            return (
              <div key={a.action} className="pl-action-row">
                <label className="pl-action-label">
                  <input type="checkbox" checked={isChecked} onChange={() => toggle(a.action)} />
                  {a.action}
                  {!inScope && <span className="pl-badge-out">hors-scope</span>}
                </label>
                {isChecked && (
                  <input
                    className="pl-resource"
                    aria-label={`ressource pour ${a.action}`}
                    placeholder="ressource (ex: acme/widgets)"
                    value={resources[a.action] ?? ""}
                    onChange={(e) =>
                      setResources((prev) => ({ ...prev, [a.action]: e.target.value }))
                    }
                  />
                )}
              </div>
            );
          })}
        </fieldset>

        <div className="pl-params">
          <label className="pl-field">
            <span>Profil attendu</span>
            <select value={profile} onChange={(e) => setProfile(e.target.value as Profile)}>
              {PROFILES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="pl-field">
            <span>Repetition</span>
            <input
              type="number"
              min={1}
              value={repeat}
              onChange={(e) => setRepeat(Number(e.target.value) || 1)}
            />
          </label>
        </div>

        <div className="pl-foot">
          <button type="button" className="btn-primary" disabled={stream.running} onClick={() => void launch()}>
            {stream.running ? "Lancement..." : "Lancer l'instance"}
          </button>
          {stream.runId !== null && (
            <span className="pl-status">
              run {stream.runId} -- {stream.status}
            </span>
          )}
        </div>

        {done && (
          <div className="pl-verdicts" data-testid="pl-verdicts">
            {verdicts.map((v) => (
              <div key={v.dimension} className={`pl-verdict pl-${v.pass ? "pass" : "fail"}`}>
                <span className="pl-dim">{v.dimension}</span>
                <span className="pl-chip">{v.pass ? "PASS" : "FAIL"}</span>
                <span className="pl-reason">{v.reason}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

```css
/* console/src/components/PreciseLaunchModal.css -- theme tokens only (no hardcoded hex) */
.pl-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.pl-modal {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  width: min(640px, 92vw);
  max-height: 88vh;
  overflow: auto;
}
.pl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pl-close {
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  cursor: pointer;
  padding: 0.1rem 0.5rem;
}
.pl-error {
  background: var(--badge-red-bg);
  color: var(--badge-red-fg);
  border-radius: 4px;
  padding: 0.5rem 0.75rem;
  margin: 0.5rem 0;
}
.pl-actions {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 0.6rem 0.85rem;
  margin: 0.75rem 0;
}
.pl-action-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.2rem 0;
}
.pl-action-label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 220px;
}
.pl-badge-out {
  font-size: 0.7rem;
  background: var(--badge-orange-bg);
  color: var(--badge-orange-fg);
  border-radius: 4px;
  padding: 0 0.3rem;
}
.pl-resource {
  flex: 1;
  background: var(--color-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 0.2rem 0.4rem;
}
.pl-params {
  display: flex;
  gap: 1rem;
}
.pl-field {
  display: flex;
  flex-direction: column;
  font-size: 0.8rem;
  gap: 0.2rem;
}
.pl-foot {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.85rem;
}
.pl-status,
.pl-muted {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.pl-verdicts {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.pl-verdict {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  border: 1px solid var(--color-border);
}
.pl-dim {
  text-transform: uppercase;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  min-width: 90px;
}
.pl-chip {
  font-weight: 700;
}
.pl-pass .pl-chip {
  color: var(--badge-green-fg);
}
.pl-fail .pl-chip {
  color: var(--badge-red-fg);
}
.pl-reason {
  font-size: 0.85rem;
}
```

**Step 4: Run tests, verify PASS**

Run: `node node_modules/.bin/vitest run src/components/PreciseLaunchModal.test.tsx`
Expected: PASS (3 cases). If a `--color-*`/`--badge-*` token is missing, confirm it exists in `src/index.css` (the dashboard already uses `--badge-green-fg`, `--badge-red-fg`, `--badge-orange-bg/fg`).

**Step 5: Commit**

```bash
git add console/src/components/PreciseLaunchModal.tsx console/src/components/PreciseLaunchModal.css console/src/components/PreciseLaunchModal.test.tsx
git commit -m "feat(dashboard): PreciseLaunchModal -- compose + launch a precise instance with inline verdict"
```

---

## Task 4: Wire the "Lancer precis" button into the dashboard

**Files:**
- Modify: `console/src/pages/dashboard/index.tsx`
- Test: `console/src/pages/dashboard/index.test.tsx` (add one case)

**Step 1: Add the failing test case** (append inside the existing `describe`)

```tsx
  it("opens the precise launch modal for an agent row", async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("kpi-succeeded")).toHaveTextContent("2"));
    fireEvent.click(screen.getByRole("button", { name: /lancer precis pour a1/i }));
    expect(
      screen.getByRole("dialog", { name: /lancer une instance precise/i }),
    ).toBeInTheDocument();
  });
```

Note: the mock list at the top of that file must also mock `listAgentActions` so the modal mount does not hit the network. Add `listAgentActions: vi.fn()` to the `vi.mock("../../api/client", ...)` return object, and in `beforeEach` add `vi.mocked(listAgentActions).mockResolvedValue([])` (import it alongside the others).

**Step 2: Run it, verify it fails**

Run: `node node_modules/.bin/vitest run src/pages/dashboard/index.test.tsx`
Expected: FAIL (no button named "Lancer precis pour a1").

**Step 3: Implement the wiring**

In `console/src/pages/dashboard/index.tsx`:

1. Add the import:
```tsx
import PreciseLaunchModal from "../../components/PreciseLaunchModal";
```

2. Add state near the other `useState` hooks:
```tsx
const [precise, setPrecise] = useState<AgentConfig | null>(null);
```

3. In the row Actions cell, add a button next to "Lancer" (inside `<div className="dash-actions">`, after the eye button):
```tsx
<button
  type="button"
  className="btn-secondary"
  aria-label={`Lancer precis pour ${agent.id}`}
  onClick={() => setPrecise(agent)}
>
  Lancer precis
</button>
```

4. Before the closing `</div>` of the page (next to `<AgentRunModal .../>`), mount:
```tsx
<PreciseLaunchModal
  open={precise !== null}
  agent={precise}
  onClose={() => {
    setPrecise(null);
    void poll();
  }}
/>
```

(If `btn-secondary` is not a known class, reuse `dash-eye` styling or `btn-primary`; the existing `index.css` defines the button primitives -- grep `btn-secondary` first and fall back to `btn-primary` if absent.)

**Step 4: Run the dashboard tests, verify PASS**

Run: `node node_modules/.bin/vitest run src/pages/dashboard/index.test.tsx`
Expected: PASS (existing 3 + new case).

**Step 5: Typecheck + full suite**

Run: `node node_modules/.bin/tsc -p tsconfig.json --noEmit`
Expected: no errors.
Run: `node node_modules/.bin/vitest run`
Expected: all green.

**Step 6: Commit**

```bash
git add console/src/pages/dashboard/index.tsx console/src/pages/dashboard/index.test.tsx
git commit -m "feat(dashboard): wire Lancer precis button to PreciseLaunchModal"
```

---

## Task 5: Help text + runbook + live verification (R14)

**Files:**
- Modify: `console/src/components/help/helpTopics.tsx` (extend the `dashboard` topic)
- Create: `docs/runbooks/precise-agent-launch.md`

**Step 1: Extend the dashboard help body**

Add a paragraph to the existing `dashboard` topic explaining: "Lancer" runs the agent in full (real-AI decides); "Lancer precis" launches a scripted *instance* -- pick actions + resource + profile + repetition -- deterministic (I4), mediated by the proxy (I5), with an inline capability/policy verdict. Keep the same JSX/markup style as the surrounding topic entries. No emoji (R10).

**Step 2: Typecheck**

Run: `node node_modules/.bin/tsc -p tsconfig.json --noEmit`
Expected: no errors.

**Step 3: Write the runbook**

`docs/runbooks/precise-agent-launch.md`: what an instance is, how to launch one, how to read the verdict (capability/policy, PASS/FAIL semantics per profile), and the note that a deny surfaces as a run failure (ProxyForge raises). Cross-link the design doc.

**Step 4: Live verification (R14 -- three proofs)**

Start API + console per the runbooks. Then, in the browser:
1. Open /dashboard, click "Lancer precis" on a known agent (e.g. `camp-marketing-bot`, target finance, empty capability_scope).
2. Pick `launch_wire_transfer`, set a resource, profile `suspect`, launch.
3. Capture: (a) the run reaches a terminal status, (b) the inline verdict renders, (c) a screenshot/snapshot of the verdict panel.

Record the three proofs in the runbook (or state the exact escape phrase from R14 if the live env is unavailable). Do NOT claim "works" without them.

**Step 5: Commit**

```bash
git add console/src/components/help/helpTopics.tsx docs/runbooks/precise-agent-launch.md
git commit -m "docs(dashboard): help + runbook for precise agent launch (instance)"
```

---

## Done criteria

- `instanceModel` unit tests green (build + judge).
- `PreciseLaunchModal` render-and-assert green against the real `/agent-actions` fixture (R16).
- Dashboard opens the modal; full vitest suite + `tsc --noEmit` clean.
- Help + runbook updated; live verification proofs captured (R14).
- No backend run change; audit log untouched (I1); scenario deterministic (I4); side effects via proxy (I5).
