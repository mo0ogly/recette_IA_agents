import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentAction, AgentConfig } from "../types/platform";
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
    vi.mocked(listAgentActions).mockResolvedValue(fixture.actions as unknown as AgentAction[]);
    vi.mocked(openRunSocket).mockReturnValue({ close: vi.fn() } as unknown as WebSocket);
    vi.mocked(launchLaneB).mockResolvedValue({ run_id: "r1", status: "pending" });
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the agent's target-system actions and pre-checks capability_scope", async () => {
    render(<PreciseLaunchModal open agent={AGENT} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByRole("checkbox", { name: /read_repo/ })).toBeChecked());
    const openPr = screen.queryByRole("checkbox", { name: /open_pr/ });
    if (openPr) expect(openPr).not.toBeChecked();
    // The pre-checked action gets a recette-realistic default resource.
    const resInput = screen.getByLabelText(/ressource pour read_repo/i) as HTMLInputElement;
    expect(resInput.value).toBe("acme/widgets");
  });

  it("blocks launch when a picked action has an empty resource", async () => {
    render(<PreciseLaunchModal open agent={AGENT} onClose={() => {}} />);
    await waitFor(() => screen.getByRole("checkbox", { name: /read_repo/ }));
    const resInput = screen.getByLabelText(/ressource pour read_repo/i) as HTMLInputElement;
    fireEvent.change(resInput, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /lancer l.instance/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/ressource/i);
    expect(launchLaneB).not.toHaveBeenCalled();
  });

  it("launches with a built scenario when valid", async () => {
    render(<PreciseLaunchModal open agent={AGENT} onClose={() => {}} />);
    await waitFor(() => screen.getByRole("checkbox", { name: /read_repo/ }));
    const resInput = screen.getByLabelText(/ressource pour read_repo/i) as HTMLInputElement;
    fireEvent.change(resInput, { target: { value: "acme/widgets" } });
    fireEvent.click(screen.getByRole("button", { name: /lancer l.instance/i }));
    await waitFor(() => expect(launchLaneB).toHaveBeenCalledTimes(1));
    const arg = vi.mocked(launchLaneB).mock.calls[0][0];
    expect(arg.agent_id).toBe("demo-gh-bot");
    expect(Array.isArray(arg.stub_script)).toBe(true);
  });

  it("surfaces a launch error from the stream", async () => {
    vi.mocked(launchLaneB).mockRejectedValue(new Error("boom"));
    render(<PreciseLaunchModal open agent={AGENT} onClose={() => {}} />);
    await waitFor(() => screen.getByRole("checkbox", { name: /read_repo/ }));
    fireEvent.change(screen.getByLabelText(/ressource pour read_repo/i), {
      target: { value: "acme/widgets" },
    });
    fireEvent.click(screen.getByRole("button", { name: /lancer l.instance/i }));
    await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument());
  });
});
