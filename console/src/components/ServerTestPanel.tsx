/**
 * ServerTestPanel: the "Test" verb of the Servers page. Fires one chosen
 * action at a running server (POST /config/servers/{id}/test) and shows its
 * raw response, exactly as a real run's proxy would (I5 path).
 *
 * The action dropdown is fed by the live catalog for the server's system
 * (getCatalog(system)); resource and payload are free input. The payload is
 * validated as JSON client-side before the call. Every failure mode is
 * surfaced inline: invalid payload, ok=false from the backend (server down,
 * bad action, transport), and a thrown request error all render an error box,
 * never a crash.
 */

import { useCallback, useEffect, useState } from "react";

import { getCatalog, testServer } from "../api/client";
import type { ActionSpec, ServerEntry, ServerTestResult } from "../types/platform";

interface ServerTestPanelProps {
  server: ServerEntry;
}

// Canonical git actions (recette/tools.py _GIT_SYSTEMS) -- these are not in the
// governance catalog, so the catalog query does not surface them. github and
// gitlab lab doubles both handle them, so offer them in the Test dropdown.
const GIT_SYSTEMS = new Set(["github", "gitlab"]);
const GIT_CANONICAL_ACTIONS = [
  "read_repo",
  "list_repos",
  "open_issue",
  "comment_issue",
  "open_pr",
  "merge_pr",
  "push",
  "manage_webhook",
];

/** Synthetic specs for the canonical git actions a git lab double handles. */
function gitCanonicalSpecs(system: string): ActionSpec[] {
  return GIT_CANONICAL_ACTIONS.map(
    (action_type) =>
      ({ action_type, risk_level: "git", target_system: system }) as unknown as ActionSpec,
  );
}

/** Parse the payload textarea: empty means {}; invalid JSON throws. */
function parsePayload(raw: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return {};
  }
  const parsed: unknown = JSON.parse(trimmed);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("payload must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export default function ServerTestPanel({ server }: ServerTestPanelProps): JSX.Element {
  const [actions, setActions] = useState<ActionSpec[]>([]);
  const [actionType, setActionType] = useState("");
  const [resource, setResource] = useState("");
  const [payload, setPayload] = useState("");
  const [result, setResult] = useState<ServerTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCatalog(server.system)
      .then((specs) => {
        if (cancelled) {
          return;
        }
        // Git systems also handle the canonical git actions (not catalogued);
        // merge them so the dropdown is never empty for github/gitlab.
        const extra = GIT_SYSTEMS.has(server.system) ? gitCanonicalSpecs(server.system) : [];
        const known = new Set(specs.map((s) => s.action_type));
        const merged = [...specs, ...extra.filter((s) => !known.has(s.action_type))];
        setActions(merged);
        if (merged.length > 0) {
          setActionType((current) => (current === "" ? merged[0].action_type : current));
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(`could not load actions for ${server.system}: ${errorText(err)}`);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [server.system]);

  const runTest = useCallback(async (): Promise<void> => {
    setError(null);
    setResult(null);
    if (actionType.trim().length === 0) {
      setError("Pick an action to test.");
      return;
    }
    let parsedPayload: Record<string, unknown>;
    try {
      parsedPayload = parsePayload(payload);
    } catch (err) {
      setError(`Invalid payload: ${errorText(err)}`);
      return;
    }
    setRunning(true);
    try {
      const res = await testServer(server.id, {
        action_type: actionType,
        resource,
        payload: parsedPayload,
      });
      setResult(res);
    } catch (err) {
      // Transport / non-2xx (400/404) surfaces here: fail-safe, no crash.
      setError(errorText(err));
    } finally {
      setRunning(false);
    }
  }, [actionType, payload, resource, server.id]);

  return (
    <div className="servers-test-panel" data-testid={`server-test-${server.id}`}>
      <div className="servers-test-form">
        <label htmlFor={`test-action-${server.id}`}>Action</label>
        <select
          id={`test-action-${server.id}`}
          value={actionType}
          onChange={(e) => setActionType(e.target.value)}
        >
          {actions.length === 0 && <option value="">(no catalog action)</option>}
          {actions.map((spec) => (
            <option key={spec.action_type} value={spec.action_type}>
              {spec.action_type} [{spec.risk_level}]
            </option>
          ))}
        </select>

        <label htmlFor={`test-resource-${server.id}`}>Resource</label>
        <input
          id={`test-resource-${server.id}`}
          type="text"
          value={resource}
          placeholder="e.g. user/alice"
          onChange={(e) => setResource(e.target.value)}
        />

        <label htmlFor={`test-payload-${server.id}`}>Payload (JSON object)</label>
        <textarea
          id={`test-payload-${server.id}`}
          value={payload}
          placeholder="{}"
          rows={3}
          onChange={(e) => setPayload(e.target.value)}
        />

        <button
          type="button"
          className="servers-btn servers-btn-primary"
          disabled={running}
          onClick={() => void runTest()}
        >
          {running ? "Running..." : "Run test"}
        </button>
      </div>

      {error !== null && (
        <div className="servers-test-error" role="alert">
          {error}
        </div>
      )}

      {result !== null && (
        <div className="servers-test-result" data-testid={`server-test-result-${server.id}`}>
          <div className="servers-test-summary">
            <span
              className={
                result.ok
                  ? "servers-dot servers-dot-up"
                  : "servers-dot servers-dot-down"
              }
              aria-hidden="true"
            />
            <span>{result.ok ? "ok" : "failed"}</span>
            {result.status_code !== undefined && <span>HTTP {result.status_code}</span>}
            <span>{result.latency_ms} ms</span>
          </div>
          {result.ok && result.side_effect_hash != null && (
            <div className="servers-test-hash">side_effect_hash: {result.side_effect_hash}</div>
          )}
          {result.ok ? (
            <pre className="servers-test-json">
              {JSON.stringify(result.response ?? {}, null, 2)}
            </pre>
          ) : (
            <div className="servers-test-error" role="alert">
              {result.error ?? "unknown error"}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
