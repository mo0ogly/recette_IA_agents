import { listPendingApprovals, ApiError } from "./client";
import type { PendingApproval } from "../types/platform";

const SAMPLE_PENDING: PendingApproval[] = [
  {
    event_id: "01JX0000000000000000000000",
    seq: 42,
    requested_at: "2026-06-12T08:00:00Z",
    agent_id: "agent-pr-bot",
    role: "developer",
    target_system: "github",
    action_type: "merge_pr",
    resource: "org/repo#17",
    risk_level: "high",
    policy_version: "v1",
  },
];

function okResponse(payload: unknown): Partial<Response> {
  return {
    ok: true,
    status: 200,
    text: async () => JSON.stringify(payload),
  };
}

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listPendingApprovals GETs /approvals?state=pending and returns parsed JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(SAMPLE_PENDING));
    vi.stubGlobal("fetch", fetchMock);

    const result = await listPendingApprovals();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8080/approvals?state=pending",
      expect.objectContaining({ method: "GET" }),
    );
    expect(result).toEqual(SAMPLE_PENDING);
  });

  it("throws an error carrying the status when the response is not ok", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "internal error",
    } as Partial<Response>);
    vi.stubGlobal("fetch", fetchMock);

    const promise = listPendingApprovals();
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(listPendingApprovals()).rejects.toThrow(/500/);
    await expect(listPendingApprovals()).rejects.toThrow(/internal error/);
  });
});
