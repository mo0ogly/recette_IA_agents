/**
 * R16 contract tests for the Servers page.
 *
 * Fixtures in __fixtures__/ were captured from the real backend
 * (recette.api running locally against a temp config), not invented.
 * The api client module is mocked so the page renders against the exact
 * payload shapes the backend returns.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ServerEntry, ServerLogTail, ServerStatus } from "../../types/platform";
import serversFixture from "./__fixtures__/servers.fixture.json";
import startUpFixture from "./__fixtures__/start-up.fixture.json";
import startBusyPortFixture from "./__fixtures__/start-busy-port.fixture.json";
import statusUpFixture from "./__fixtures__/status-up.fixture.json";
import statusDownFixture from "./__fixtures__/status-down.fixture.json";
import statusNaFixture from "./__fixtures__/status-na.fixture.json";
import stopFixture from "./__fixtures__/stop.fixture.json";
import logTailFixture from "./__fixtures__/log-tail.fixture.json";
import create400Fixture from "./__fixtures__/create-400-detail.fixture.json";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listServers: vi.fn(),
    createServer: vi.fn(),
    updateServer: vi.fn(),
    deleteServer: vi.fn(),
    startServer: vi.fn(),
    stopServer: vi.fn(),
    getServerStatus: vi.fn(),
    getServerLog: vi.fn(),
    getCatalog: vi.fn(),
    testServer: vi.fn(),
  };
});

import {
  ApiError,
  createServer,
  deleteServer,
  getCatalog,
  getServerLog,
  getServerStatus,
  listServers,
  startServer,
  stopServer,
} from "../../api/client";
import ServersPage from "./index";

const servers = serversFixture as ServerEntry[];
const logTail = logTailFixture as ServerLogTail;

/** Statuses captured from the real backend, one per fixture server. */
const STATUS_BY_ID: Record<string, { status: ServerStatus }> = {
  "gh-mock": statusUpFixture as { status: ServerStatus },
  "gl-staging": statusDownFixture as { status: ServerStatus },
  "gh-saas": statusNaFixture as { status: ServerStatus },
};

function mockHappyList(): void {
  vi.mocked(listServers).mockResolvedValue(servers);
  vi.mocked(getServerStatus).mockImplementation((id) =>
    Promise.resolve(STATUS_BY_ID[id] ?? { status: "down" }),
  );
}

/** Switch to the "Configuration" tab where the create/edit form lives. */
function openConfigTab(): void {
  fireEvent.click(screen.getByRole("tab", { name: "Configuration" }));
}

/** The table row of one server, located by its id cell (waits for the list). */
async function rowOf(id: string): Promise<HTMLElement> {
  const cell = await screen.findByText(id);
  const row = cell.closest("tr");
  if (row === null) {
    throw new Error(`no table row for server ${id}`);
  }
  return row;
}

describe("ServersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the three modes with their targets and status dots", async () => {
    mockHappyList();

    render(<ServersPage />);

    // One row per fixture server, each showing its mode label.
    expect(await screen.findByText("gh-mock")).toBeInTheDocument();
    expect(screen.getByText("mock_local")).toBeInTheDocument();
    expect(screen.getByText("declared_url")).toBeInTheDocument();
    expect(screen.getByText("real_saas")).toBeInTheDocument();

    // Mode-dependent target column.
    expect(screen.getByText("port 9101")).toBeInTheDocument();
    expect(screen.getByText("http://127.0.0.1:9555")).toBeInTheDocument();
    expect(screen.getByText("inspect_ia_agents-recette")).toBeInTheDocument();

    // Status text + colored dot per server (up=green, down=red, n/a=grey).
    expect(await within(await rowOf("gh-mock")).findByText("up")).toBeInTheDocument();
    expect(within(await rowOf("gl-staging")).getByText("down")).toBeInTheDocument();
    expect(within(await rowOf("gh-saas")).getByText("n/a")).toBeInTheDocument();
    expect(screen.getByTestId("server-dot-gh-mock")).toHaveClass("servers-dot-up");
    expect(screen.getByTestId("server-dot-gl-staging")).toHaveClass("servers-dot-down");
    expect(screen.getByTestId("server-dot-gh-saas")).toHaveClass("servers-dot-na");

    // Start/Stop only for mock_local rows.
    expect(within(await rowOf("gh-mock")).getByRole("button", { name: "Start" })).toBeInTheDocument();
    expect(within(await rowOf("gl-staging")).queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
    expect(within(await rowOf("gh-saas")).queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();

    // No error banner on the happy path.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("starts a mock_local server and renders the captured up status", async () => {
    vi.mocked(listServers).mockResolvedValue(servers);
    // The server is down before the user clicks Start.
    vi.mocked(getServerStatus).mockResolvedValue(statusDownFixture as { status: ServerStatus });
    vi.mocked(startServer).mockResolvedValue(startUpFixture as { status: ServerStatus });

    render(<ServersPage />);

    const row = await rowOf("gh-mock");
    await within(row).findByText("down");
    fireEvent.click(within(row).getByRole("button", { name: "Start" }));

    expect(startServer).toHaveBeenCalledWith("gh-mock");
    expect(await within(await rowOf("gh-mock")).findByText("up")).toBeInTheDocument();
  });

  it("renders the busy-port error text from the captured start response", async () => {
    mockHappyList();
    vi.mocked(startServer).mockResolvedValue(
      startBusyPortFixture as { status: ServerStatus; error: string },
    );

    render(<ServersPage />);

    const row = await rowOf("gh-mock");
    await within(row).findByText("up");
    fireEvent.click(within(row).getByRole("button", { name: "Start" }));

    expect(
      await screen.findByText(
        "port 9102 already in use: [Errno 98] Address already in use",
      ),
    ).toBeInTheDocument();
    // The lifecycle result also flips the row status to down.
    expect(within(await rowOf("gh-mock")).getByText("down")).toBeInTheDocument();
  });

  it("stops a mock_local server and renders down", async () => {
    mockHappyList();
    vi.mocked(stopServer).mockResolvedValue(stopFixture as { status: ServerStatus });

    render(<ServersPage />);

    const row = await rowOf("gh-mock");
    await within(row).findByText("up");
    fireEvent.click(within(row).getByRole("button", { name: "Stop" }));

    expect(stopServer).toHaveBeenCalledWith("gh-mock");
    expect(await within(await rowOf("gh-mock")).findByText("down")).toBeInTheDocument();
  });

  it("opens the log panel and renders the captured access-log lines", async () => {
    mockHappyList();
    vi.mocked(getServerLog).mockResolvedValue(logTail);

    render(<ServersPage />);

    const row = await rowOf("gh-mock");
    await within(row).findByText("up");
    fireEvent.click(within(row).getByRole("button", { name: "View log" }));

    const panel = await screen.findByTestId("server-log-gh-mock");
    expect(getServerLog).toHaveBeenCalledWith("gh-mock", 0);
    // The panel is the reusable LogConsole, titled per server.
    expect(within(panel).getByText("Access log (gh-mock)")).toBeInTheDocument();
    // Fields of the captured log line (the tail loads asynchronously).
    await waitFor(() => expect(panel.textContent).toContain("delete_repository"));
    expect(panel.textContent).toContain("e1");
    expect(panel.textContent).toContain("github");
    expect(panel.textContent).toContain("acme/x");
    expect(panel.textContent).toContain("200");
    // A 2xx access-log entry renders as an info-level line.
    const infoLine = within(panel).getByText(/e1 delete_repository/).closest(".logc-line");
    expect(infoLine).toHaveAttribute("data-level", "info");

    // Toggle off removes the panel.
    fireEvent.click(within(await rowOf("gh-mock")).getByRole("button", { name: "Hide log" }));
    expect(screen.queryByTestId("server-log-gh-mock")).not.toBeInTheDocument();
  });

  it("renders a 4xx access-log entry as an error-level line", async () => {
    mockHappyList();
    // Derived from the captured tail fixture: same line shape, denied status.
    const deniedTail: ServerLogTail = {
      lines: [{ ...logTail.lines[0], event_id: "e2", status: 403 }],
      next: 2,
    };
    vi.mocked(getServerLog).mockResolvedValue(deniedTail);

    render(<ServersPage />);

    const row = await rowOf("gh-mock");
    await within(row).findByText("up");
    fireEvent.click(within(row).getByRole("button", { name: "View log" }));

    const panel = await screen.findByTestId("server-log-gh-mock");
    const line = await within(panel).findByText(/e2 delete_repository acme\/x 403/);
    expect(line.closest(".logc-line")).toHaveAttribute("data-level", "error");
  });

  it("toggles the Test panel on probeable servers but hides it for real_saas", async () => {
    mockHappyList();
    vi.mocked(getCatalog).mockResolvedValue([]);

    render(<ServersPage />);

    // real_saas cannot be probed: no Test button.
    expect(
      within(await rowOf("gh-saas")).queryByRole("button", { name: "Test" }),
    ).not.toBeInTheDocument();

    // mock_local exposes Test; clicking opens the panel for that server.
    const row = await rowOf("gh-mock");
    await within(row).findByText("up");
    fireEvent.click(within(row).getByRole("button", { name: "Test" }));

    expect(await screen.findByTestId("server-test-gh-mock")).toBeInTheDocument();
    expect(getCatalog).toHaveBeenCalledWith("github");

    // Toggle off removes the panel.
    fireEvent.click(within(await rowOf("gh-mock")).getByRole("button", { name: "Hide test" }));
    expect(screen.queryByTestId("server-test-gh-mock")).not.toBeInTheDocument();
  });

  it("defaults to the Serveurs tab and hides the form until Configuration is selected", async () => {
    mockHappyList();

    render(<ServersPage />);
    await screen.findByText("gh-mock");

    // List tab is active: the table is shown, the form is not mounted.
    expect(screen.getByRole("tab", { name: "Serveurs" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.queryByLabelText("System")).not.toBeInTheDocument();

    openConfigTab();
    expect(screen.getByRole("tab", { name: "Configuration" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByLabelText("System")).toBeInTheDocument();
  });

  it("Edit on a row jumps to the Configuration tab pre-filled with that server", async () => {
    mockHappyList();

    render(<ServersPage />);
    const row = await rowOf("gh-mock");
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));

    // The form tab is now active, populated from the edited server.
    expect(screen.getByRole("tab", { name: "Configuration" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Edit server gh-mock")).toBeInTheDocument();
    expect((screen.getByLabelText("System") as HTMLInputElement).value).toBe("github");
  });

  it("shows mode-dependent form fields (port vs base_url vs owner)", async () => {
    vi.mocked(listServers).mockResolvedValue([]);

    render(<ServersPage />);
    await screen.findByText("No servers configured.");
    openConfigTab();

    // Default mode is mock_local: port field only.
    expect(screen.getByLabelText("Port")).toBeInTheDocument();
    expect(screen.queryByLabelText("Base URL")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Owner")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Mode"), {
      target: { value: "declared_url" },
    });
    expect(screen.getByLabelText("Base URL")).toBeInTheDocument();
    expect(screen.queryByLabelText("Port")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Mode"), {
      target: { value: "real_saas" },
    });
    expect(screen.getByLabelText("Owner")).toBeInTheDocument();
    expect(screen.queryByLabelText("Base URL")).not.toBeInTheDocument();
  });

  it("creates a server with only the mode's target field in the payload", async () => {
    vi.mocked(listServers).mockResolvedValue([]);
    vi.mocked(createServer).mockResolvedValue(servers[1]);

    render(<ServersPage />);
    await screen.findByText("No servers configured.");
    openConfigTab();

    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "gl-staging" } });
    fireEvent.change(screen.getByLabelText("System"), { target: { value: "gitlab" } });
    fireEvent.change(screen.getByLabelText("Mode"), {
      target: { value: "declared_url" },
    });
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "http://127.0.0.1:9555" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(createServer).toHaveBeenCalledTimes(1);
    expect(vi.mocked(createServer).mock.calls[0][0]).toEqual({
      id: "gl-staging",
      system: "gitlab",
      mode: "declared_url",
      base_url: "http://127.0.0.1:9555",
    });
    // A successful create resets the form (flushes the post-submit refresh).
    await waitFor(() =>
      expect((screen.getByLabelText("Id") as HTMLInputElement).value).toBe(""),
    );
  });

  it("blocks a mock_local create without a port (client-side validation)", async () => {
    vi.mocked(listServers).mockResolvedValue([]);

    render(<ServersPage />);
    await screen.findByText("No servers configured.");
    openConfigTab();

    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "gh-mock" } });
    fireEvent.change(screen.getByLabelText("System"), { target: { value: "github" } });
    // Port left empty: submit must not reach the API.
    fireEvent.submit(screen.getByRole("button", { name: "Create" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mode mock_local requires a port.",
    );
    expect(createServer).not.toHaveBeenCalled();
  });

  it("surfaces the backend 400 detail text from the captured error body", async () => {
    vi.mocked(listServers).mockResolvedValue([]);
    vi.mocked(createServer).mockRejectedValue(
      new ApiError(400, "/config/servers", JSON.stringify(create400Fixture)),
    );

    render(<ServersPage />);
    await screen.findByText("No servers configured.");
    openConfigTab();

    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "bad" } });
    fireEvent.change(screen.getByLabelText("System"), { target: { value: "github" } });
    fireEvent.change(screen.getByLabelText("Port"), { target: { value: "9102" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      create400Fixture.detail,
    );
  });

  it("deletes a server only after the user confirms", async () => {
    mockHappyList();
    vi.mocked(deleteServer).mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm");

    render(<ServersPage />);
    const row = await rowOf("gh-saas");
    await within(await rowOf("gh-mock")).findByText("up");

    confirmSpy.mockReturnValueOnce(false);
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    expect(deleteServer).not.toHaveBeenCalled();

    confirmSpy.mockReturnValueOnce(true);
    fireEvent.click(within(await rowOf("gh-saas")).getByRole("button", { name: "Delete" }));
    expect(deleteServer).toHaveBeenCalledWith("gh-saas");
    // The post-delete refresh re-fetches the list (flushes pending updates).
    await waitFor(() => expect(listServers).toHaveBeenCalledTimes(2));
  });
});
