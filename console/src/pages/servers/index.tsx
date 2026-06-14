/**
 * Servers page: target servers agents act against (GET /config/servers).
 *
 * Lists servers with a live status dot, supports create / edit / delete,
 * starts and stops mock_local servers, and tails each server's access log
 * into the reusable LogConsole. Credentials are referenced by env var name
 * only (auth_env, R8): no secret is ever displayed or submitted here.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  createServer,
  deleteServer,
  getServerLog,
  getServerStatus,
  listServers,
  startServer,
  stopServer,
  updateServer,
} from "../../api/client";
import type {
  ServerEntry,
  ServerLogLine,
  ServerMode,
  ServerStatus,
} from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import ServerTestPanel from "../../components/ServerTestPanel";
import { LogConsole } from "../../components/LogConsole";
import type { LogLine } from "../../components/LogConsole";
import "./servers.css";

/** Incremental poll period of an open log panel. */
const LOG_POLL_INTERVAL_MS = 2000;

/** The two views of the page, split into tabs. */
type ServersTab = "list" | "config";
const TABS: ReadonlyArray<{ key: ServersTab; label: string }> = [
  { key: "list", label: "Serveurs" },
  { key: "config", label: "Configuration" },
];

const MODE_LABELS: Record<ServerMode, string> = {
  mock_local: "mock_local",
  declared_url: "declared_url",
  real_saas: "real_saas",
};

/** Form state: every field as the raw string the user types. */
interface ServerFormValues {
  id: string;
  system: string;
  mode: ServerMode;
  port: string;
  baseUrl: string;
  owner: string;
  authEnv: string;
}

const EMPTY_FORM: ServerFormValues = {
  id: "",
  system: "",
  mode: "mock_local",
  port: "",
  baseUrl: "",
  owner: "",
  authEnv: "",
};

/** The mode-dependent target shown in the table (port / base_url / owner). */
function targetOf(server: ServerEntry): string {
  switch (server.mode) {
    case "mock_local":
      return server.port !== undefined ? `port ${server.port}` : "";
    case "declared_url":
      return server.base_url ?? "";
    case "real_saas":
      return server.owner ?? "";
  }
}

/** Client-side validation mirroring the backend _check_server rules. */
function validateForm(values: ServerFormValues, id: string): string | null {
  if (id.length === 0) {
    return "Server id is required.";
  }
  if (values.system.trim().length === 0) {
    return "Server system is required.";
  }
  if (values.mode === "mock_local") {
    if (values.port.trim().length === 0) {
      return "Mode mock_local requires a port.";
    }
    if (!/^\d+$/.test(values.port.trim())) {
      return "Port must be an integer.";
    }
  }
  if (values.mode === "declared_url" && values.baseUrl.trim().length === 0) {
    return "Mode declared_url requires a base URL.";
  }
  if (values.mode === "real_saas" && values.owner.trim().length === 0) {
    return "Mode real_saas requires an owner.";
  }
  return null;
}

/** Build the API payload from the form; only the mode's target field is sent. */
function toServerEntry(values: ServerFormValues, id: string): ServerEntry {
  const entry: ServerEntry = {
    id,
    system: values.system.trim(),
    mode: values.mode,
  };
  if (values.mode === "mock_local") {
    entry.port = Number.parseInt(values.port.trim(), 10);
  } else if (values.mode === "declared_url") {
    entry.base_url = values.baseUrl.trim();
  } else {
    entry.owner = values.owner.trim();
  }
  const authEnv = values.authEnv.trim();
  if (authEnv.length > 0) {
    entry.auth_env = authEnv;
  }
  return entry;
}

/** Load an existing server into the form for editing. */
function toFormValues(server: ServerEntry): ServerFormValues {
  return {
    id: server.id,
    system: server.system,
    mode: server.mode,
    port: server.port !== undefined ? String(server.port) : "",
    baseUrl: server.base_url ?? "",
    owner: server.owner ?? "",
    authEnv: server.auth_env ?? "",
  };
}

/** Surface the backend "detail" text of a 400/404 body when present. */
function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.message.match(/\{.*\}\s*$/s);
    if (body !== null) {
      try {
        const parsed: unknown = JSON.parse(body[0]);
        if (
          typeof parsed === "object" &&
          parsed !== null &&
          typeof (parsed as { detail?: unknown }).detail === "string"
        ) {
          return (parsed as { detail: string }).detail;
        }
      } catch {
        // Not a JSON body: fall through to the raw message.
      }
    }
  }
  return err instanceof Error ? err.message : String(err);
}

function dotClass(status: ServerStatus | undefined): string {
  switch (status) {
    case "up":
      return "servers-dot servers-dot-up";
    case "down":
      return "servers-dot servers-dot-down";
    default:
      return "servers-dot servers-dot-na";
  }
}

/** Map one accumulated access-log entry to a displayable log line.
 *  HTTP status >= 400 (denied / failed proxy call) is error-level. */
function serverLogToLogLine(line: ServerLogLine, index: number): LogLine {
  return {
    seq: index + 1,
    level: line.status >= 400 ? "error" : "info",
    source: line.target_system,
    text: `${line.event_id} ${line.action_type} ${line.resource} ${line.status}`,
  };
}

/** Incremental tail of one server's access log into the reusable LogConsole. */
function ServerLogPanel({ serverId }: { serverId: string }): JSX.Element {
  const [lines, setLines] = useState<ServerLogLine[]>([]);
  const cursorRef = useRef(0);
  const busyRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    async function poll(): Promise<void> {
      if (busyRef.current) {
        // A previous poll is still in flight: skip this tick (no overlap).
        return;
      }
      busyRef.current = true;
      try {
        const tail = await getServerLog(serverId, cursorRef.current);
        if (cancelled) {
          return;
        }
        cursorRef.current = tail.next;
        if (tail.lines.length > 0) {
          setLines((prev) => [...prev, ...tail.lines]);
        }
      } catch {
        // Best-effort tail: a failed poll is retried on the next tick.
      } finally {
        busyRef.current = false;
      }
    }
    void poll();
    const timer = window.setInterval(() => void poll(), LOG_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [serverId]);

  return (
    <div className="servers-log-panel" data-testid={`server-log-${serverId}`}>
      <LogConsole
        title={`Access log (${serverId})`}
        lines={lines.map(serverLogToLogLine)}
      />
    </div>
  );
}

export default function ServersPage(): JSX.Element {
  const [servers, setServers] = useState<ServerEntry[]>([]);
  const [statuses, setStatuses] = useState<Record<string, ServerStatus>>({});
  const [lifecycleErrors, setLifecycleErrors] = useState<Record<string, string>>({});
  const [openLogs, setOpenLogs] = useState<Record<string, boolean>>({});
  const [openTests, setOpenTests] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // null means the form is in create mode; otherwise the id being edited.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ServerFormValues>(EMPTY_FORM);
  const [tab, setTab] = useState<ServersTab>("list");

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const serverList = await listServers();
      setServers(serverList);
      setError(null);
      const entries = await Promise.all(
        serverList.map(async (server): Promise<[string, ServerStatus]> => {
          try {
            const res = await getServerStatus(server.id);
            return [server.id, res.status];
          } catch {
            // Fail-safe: an unreachable status probe renders as "down".
            return [server.id, "down"];
          }
        }),
      );
      setStatuses(Object.fromEntries(entries));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function setField<K extends keyof ServerFormValues>(
    key: K,
    value: ServerFormValues[K],
  ): void {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function setLifecycle(id: string, status: ServerStatus, message?: string): void {
    setStatuses((prev) => ({ ...prev, [id]: status }));
    setLifecycleErrors((prev) => {
      const next = { ...prev };
      if (message !== undefined) {
        next[id] = message;
      } else {
        delete next[id];
      }
      return next;
    });
  }

  function startEdit(server: ServerEntry): void {
    setEditingId(server.id);
    setForm(toFormValues(server));
    setTab("config");
  }

  function cancelEdit(): void {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const id = editingId ?? form.id.trim();
    const validation = validateForm(form, id);
    if (validation !== null) {
      setError(validation);
      return;
    }
    try {
      const payload = toServerEntry(form, id);
      if (editingId === null) {
        await createServer(payload);
      } else {
        await updateServer(editingId, payload);
      }
      cancelEdit();
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDelete(id: string): Promise<void> {
    if (!window.confirm(`Delete server "${id}"?`)) {
      return;
    }
    try {
      await deleteServer(id);
      if (editingId === id) {
        cancelEdit();
      }
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleStart(id: string): Promise<void> {
    try {
      const result = await startServer(id);
      setLifecycle(id, result.status, result.error);
    } catch (err) {
      setLifecycle(id, "down", errorMessage(err));
    }
  }

  async function handleStop(id: string): Promise<void> {
    try {
      const result = await stopServer(id);
      setLifecycle(id, result.status, result.error);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function toggleLog(id: string): void {
    setOpenLogs((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function toggleTest(id: string): void {
    setOpenTests((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <div>
      <div className="page-head">
        <h1>Serveurs</h1>
        <PageHelp topic="servers" />
      </div>

      {error !== null && (
        <div className="servers-error-banner" role="alert">
          {error}
        </div>
      )}

      <div className="run-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={tab === t.key ? "run-tab run-tab-active" : "run-tab"}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "list" && (
        <section className="panel" role="tabpanel">
      <table className="servers-table">
        <thead>
          <tr>
            <th>Id</th>
            <th>System</th>
            <th>Mode</th>
            <th>Target</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {loaded && servers.length === 0 ? (
            <tr>
              <td colSpan={6} className="servers-empty">
                No servers configured.
              </td>
            </tr>
          ) : (
            servers.flatMap((server) => {
              const status = statuses[server.id];
              const lifecycleError = lifecycleErrors[server.id];
              const rows = [
                <tr key={server.id}>
                  <td>{server.id}</td>
                  <td>{server.system}</td>
                  <td>
                    <span className="servers-mode">{MODE_LABELS[server.mode]}</span>
                  </td>
                  <td>{targetOf(server)}</td>
                  <td>
                    <span className="servers-status">
                      <span
                        className={dotClass(status)}
                        data-testid={`server-dot-${server.id}`}
                        aria-hidden="true"
                      />
                      {status ?? "..."}
                    </span>
                    {lifecycleError !== undefined && (
                      <span className="servers-lifecycle-error" role="alert">
                        {lifecycleError}
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="servers-row-actions">
                      {server.mode === "mock_local" && (
                        <>
                          <button
                            type="button"
                            className="servers-btn servers-btn-primary"
                            onClick={() => void handleStart(server.id)}
                          >
                            Start
                          </button>
                          <button
                            type="button"
                            className="servers-btn"
                            onClick={() => void handleStop(server.id)}
                          >
                            Stop
                          </button>
                        </>
                      )}
                      {server.mode !== "real_saas" && (
                        <button
                          type="button"
                          className="servers-btn"
                          onClick={() => toggleTest(server.id)}
                        >
                          {openTests[server.id] ? "Hide test" : "Test"}
                        </button>
                      )}
                      <button
                        type="button"
                        className="servers-btn"
                        onClick={() => toggleLog(server.id)}
                      >
                        {openLogs[server.id] ? "Hide log" : "View log"}
                      </button>
                      <button
                        type="button"
                        className="servers-btn"
                        onClick={() => startEdit(server)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="servers-btn servers-btn-danger"
                        onClick={() => void handleDelete(server.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>,
              ];
              if (openTests[server.id]) {
                rows.push(
                  <tr key={`${server.id}-test`}>
                    <td colSpan={6}>
                      <ServerTestPanel server={server} />
                    </td>
                  </tr>,
                );
              }
              if (openLogs[server.id]) {
                rows.push(
                  <tr key={`${server.id}-log`}>
                    <td colSpan={6}>
                      <ServerLogPanel serverId={server.id} />
                    </td>
                  </tr>,
                );
              }
              return rows;
            })
          )}
        </tbody>
      </table>
        </section>
      )}

      {tab === "config" && (
        <section className="panel" role="tabpanel">
      <form className="servers-form" onSubmit={(e) => void handleSubmit(e)}>
        <h2>{editingId === null ? "Create server" : `Edit server ${editingId}`}</h2>

        {editingId === null && (
          <div className="servers-form-row">
            <label htmlFor="server-id">Id</label>
            <input
              id="server-id"
              type="text"
              value={form.id}
              onChange={(e) => setField("id", e.target.value)}
              required
            />
          </div>
        )}

        <div className="servers-form-row">
          <label htmlFor="server-system">System</label>
          <input
            id="server-system"
            type="text"
            value={form.system}
            onChange={(e) => setField("system", e.target.value)}
            required
          />
        </div>

        <div className="servers-form-row">
          <label htmlFor="server-mode">Mode</label>
          <select
            id="server-mode"
            value={form.mode}
            onChange={(e) => setField("mode", e.target.value as ServerMode)}
          >
            <option value="mock_local">mock_local (local mock process)</option>
            <option value="declared_url">declared_url (existing server)</option>
            <option value="real_saas">real_saas (SaaS platform)</option>
          </select>
        </div>

        {form.mode === "mock_local" && (
          <div className="servers-form-row">
            <label htmlFor="server-port">Port</label>
            <input
              id="server-port"
              type="number"
              value={form.port}
              onChange={(e) => setField("port", e.target.value)}
              required
            />
          </div>
        )}

        {form.mode === "declared_url" && (
          <div className="servers-form-row">
            <label htmlFor="server-base-url">Base URL</label>
            <input
              id="server-base-url"
              type="text"
              value={form.baseUrl}
              onChange={(e) => setField("baseUrl", e.target.value)}
              required
            />
          </div>
        )}

        {form.mode === "real_saas" && (
          <div className="servers-form-row">
            <label htmlFor="server-owner">Owner</label>
            <input
              id="server-owner"
              type="text"
              value={form.owner}
              onChange={(e) => setField("owner", e.target.value)}
              required
            />
          </div>
        )}

        <div className="servers-form-row">
          <label htmlFor="server-auth-env">Auth env var (name only, no secret)</label>
          <input
            id="server-auth-env"
            type="text"
            value={form.authEnv}
            onChange={(e) => setField("authEnv", e.target.value)}
          />
        </div>

        <div className="servers-form-actions">
          <button type="submit" className="servers-btn servers-btn-primary">
            {editingId === null ? "Create" : "Save"}
          </button>
          {editingId !== null && (
            <button type="button" className="servers-btn" onClick={cancelEdit}>
              Cancel
            </button>
          )}
        </div>
      </form>
        </section>
      )}
    </div>
  );
}
