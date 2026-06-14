/**
 * ServerTestPanel tests (R16 contract gate).
 *
 * The success fixture (serverTest.fixture.json) is a payload CAPTURED live from
 * POST /config/servers/{id}/test against a real lab server, not invented. The
 * client module is mocked: getCatalog feeds the action dropdown, testServer
 * returns the captured fixture. Covers the happy path (response rendered), the
 * fail-safe ok=false branch, and client-side payload validation.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import testFixture from "./__fixtures__/serverTest.fixture.json";
import type { ActionSpec, ServerEntry, ServerTestResult } from "../types/platform";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    getCatalog: vi.fn(),
    testServer: vi.fn(),
  };
});

import { getCatalog, testServer } from "../api/client";
import ServerTestPanel from "./ServerTestPanel";

const SERVER: ServerEntry = {
  id: "okta-mock",
  system: "okta",
  mode: "mock_local",
  port: 9122,
};

const ACTIONS: ActionSpec[] = [
  {
    target_system: "okta",
    action_type: "suspend_user",
    risk_level: "high",
    risk_score: 3,
    criticality: "C3",
    criticality_label: "conditional authorization",
    verdict_privileged: "escalate",
    verdict_default: "deny",
    privileged_roles: ["identity_admin"],
    description: "Suspend a user account.",
  },
  {
    target_system: "okta",
    action_type: "list_users",
    risk_level: "low",
    risk_score: 1,
    criticality: "C4",
    criticality_label: "authorization with logging",
    verdict_privileged: "allow",
    verdict_default: "allow",
    privileged_roles: [],
    description: "List users.",
  },
];

const okResult = testFixture as unknown as ServerTestResult;

describe("ServerTestPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getCatalog).mockResolvedValue(ACTIONS);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the system's actions into the dropdown", async () => {
    render(<ServerTestPanel server={SERVER} />);
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toHaveValue("suspend_user");
    });
    expect(screen.getByRole("option", { name: /list_users/ })).toBeInTheDocument();
  });

  it("runs the test and renders the captured server response", async () => {
    vi.mocked(testServer).mockResolvedValue(okResult);
    render(<ServerTestPanel server={SERVER} />);
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("suspend_user"));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run test" }));
    });

    expect(vi.mocked(testServer)).toHaveBeenCalledWith("okta-mock", {
      action_type: "suspend_user",
      resource: "",
      payload: {},
    });
    const result = screen.getByTestId("server-test-result-okta-mock");
    expect(result).toHaveTextContent("ok");
    expect(result).toHaveTextContent("HTTP 200");
    expect(result).toHaveTextContent("SUSPENDED");
    expect(result).toHaveTextContent(/side_effect_hash:/);
  });

  it("renders the error box when the backend reports ok=false", async () => {
    const failResult: ServerTestResult = {
      ok: false,
      latency_ms: 1,
      status_code: 0,
      error: "proxy transport error: connection refused",
    };
    vi.mocked(testServer).mockResolvedValue(failResult);
    render(<ServerTestPanel server={SERVER} />);
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("suspend_user"));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run test" }));
    });

    expect(screen.getByRole("alert")).toHaveTextContent("connection refused");
  });

  it("rejects an invalid JSON payload before calling the backend", async () => {
    render(<ServerTestPanel server={SERVER} />);
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("suspend_user"));

    fireEvent.change(screen.getByLabelText(/Payload/), { target: { value: "{not json" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run test" }));
    });

    expect(screen.getByRole("alert")).toHaveTextContent(/Invalid payload/);
    expect(vi.mocked(testServer)).not.toHaveBeenCalled();
  });
});
