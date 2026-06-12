/**
 * Catalog + Policy editor page.
 *
 * Left: the governed action catalog (GET /catalog/actions) with a
 * target_system filter. Right: the active policy version, with an edit mode
 * that lets an operator change rule verdicts and publish the result as a new
 * immutable policy version (I1: versions are append-only; publishing never
 * mutates an existing document).
 *
 * R16 note: the backend wraps the catalog payload as { actions, count } and
 * the policy list as { versions, active }. The shared client is typed as bare
 * arrays, so this page unwraps both shapes explicitly before rendering
 * (fixtures captured from the real backend live in __fixtures__/).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../../api/client";
import { StatusBadge } from "../../components/StatusBadge";
import type {
  ActionSpec,
  PolicyDocument,
  PolicyRule,
  PolicyVerdict,
} from "../../types/platform";
import PageHelp from "../../components/help/PageHelp";
import "./catalog.css";

const VERDICTS: PolicyVerdict[] = ["allow", "deny", "escalate"];

/** Accepts either a bare ActionSpec[] or the backend envelope { actions, count }. */
function unwrapActions(payload: unknown): ActionSpec[] {
  if (Array.isArray(payload)) {
    return payload as ActionSpec[];
  }
  if (payload !== null && typeof payload === "object") {
    const actions = (payload as { actions?: unknown }).actions;
    if (Array.isArray(actions)) {
      return actions as ActionSpec[];
    }
  }
  return [];
}

/** Accepts either PolicyDocument[] or the backend envelope { versions, active }. */
function unwrapVersions(payload: unknown): string[] {
  if (Array.isArray(payload)) {
    return (payload as PolicyDocument[]).map((doc) => doc.version);
  }
  if (payload !== null && typeof payload === "object") {
    const versions = (payload as { versions?: unknown }).versions;
    if (Array.isArray(versions)) {
      return versions.filter((v): v is string => typeof v === "string");
    }
  }
  return [];
}

function errorMessage(err: unknown): string {
  if (err instanceof api.ApiError && err.status === 409) {
    return `Version conflict (409): a policy with this version already exists. ${err.message}`;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}

interface CatalogTableProps {
  actions: ActionSpec[];
}

function CatalogTable({ actions }: CatalogTableProps): JSX.Element {
  return (
    <table className="catalog-table">
      <thead>
        <tr>
          <th>Target system</th>
          <th>Action type</th>
          <th>Risk</th>
          <th>Verdict (privileged)</th>
          <th>Verdict (default)</th>
          <th>Privileged roles</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        {actions.map((spec) => (
          <tr key={`${spec.target_system}.${spec.action_type}`}>
            <td>{spec.target_system}</td>
            <td>{spec.action_type}</td>
            <td>
              <StatusBadge kind="risk" value={spec.risk_level} />
            </td>
            <td>
              <StatusBadge kind="verdict" value={spec.verdict_privileged} />
            </td>
            <td>
              <StatusBadge kind="verdict" value={spec.verdict_default} />
            </td>
            <td>{spec.privileged_roles.join(", ")}</td>
            <td className="catalog-description">{spec.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface PolicyEditorProps {
  draft: PolicyRule[];
  newVersion: string;
  publishing: boolean;
  onVerdictChange: (ruleId: string, verdict: PolicyVerdict) => void;
  onVersionChange: (value: string) => void;
  onPublish: () => void;
  onCancel: () => void;
}

function PolicyEditor(props: PolicyEditorProps): JSX.Element {
  return (
    <div className="policy-editor">
      <div className="policy-publish-bar">
        <label className="policy-version-label" htmlFor="new-policy-version">
          New version
        </label>
        <input
          id="new-policy-version"
          className="policy-version-input"
          type="text"
          value={props.newVersion}
          placeholder="e.g. v2"
          onChange={(e) => props.onVersionChange(e.target.value)}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={props.publishing}
          onClick={props.onPublish}
        >
          Publish as new version
        </button>
        <button
          type="button"
          className="btn"
          disabled={props.publishing}
          onClick={props.onCancel}
        >
          Cancel
        </button>
      </div>
      <table className="policy-rules-table">
        <thead>
          <tr>
            <th>Rule</th>
            <th>Role</th>
            <th>Risk</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {props.draft.map((rule) => (
            <tr key={rule.rule_id}>
              <td>
                {rule.target_system}.{rule.action_type}
              </td>
              <td>{rule.role}</td>
              <td>
                <StatusBadge kind="risk" value={rule.risk_level} />
              </td>
              <td>
                <select
                  aria-label={`Verdict for ${rule.rule_id}`}
                  value={rule.verdict}
                  onChange={(e) =>
                    props.onVerdictChange(rule.rule_id, e.target.value as PolicyVerdict)
                  }
                >
                  {VERDICTS.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CatalogPage(): JSX.Element {
  const [actions, setActions] = useState<ActionSpec[] | null>(null);
  const [systemFilter, setSystemFilter] = useState<string>("");
  const [activePolicy, setActivePolicyDoc] = useState<PolicyDocument | null>(null);
  const [versions, setVersions] = useState<string[]>([]);
  const [draft, setDraft] = useState<PolicyRule[] | null>(null);
  const [newVersion, setNewVersion] = useState<string>("");
  const [publishing, setPublishing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [catalogPayload, activeDoc, policiesPayload] = await Promise.all([
        api.getCatalog(),
        api.getActivePolicy(),
        api.listPolicies(),
      ]);
      setActions(unwrapActions(catalogPayload));
      setActivePolicyDoc(activeDoc);
      setVersions(unwrapVersions(policiesPayload));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const systems = useMemo(() => {
    const unique = new Set<string>();
    for (const spec of actions ?? []) {
      unique.add(spec.target_system);
    }
    return Array.from(unique).sort();
  }, [actions]);

  const visible = useMemo(() => {
    if (actions === null) {
      return [];
    }
    if (systemFilter === "") {
      return actions;
    }
    return actions.filter((spec) => spec.target_system === systemFilter);
  }, [actions, systemFilter]);

  const startEditing = useCallback(() => {
    if (activePolicy === null) {
      return;
    }
    setDraft(activePolicy.rules.map((rule) => ({ ...rule })));
    setNewVersion("");
    setNotice(null);
    setError(null);
  }, [activePolicy]);

  const changeVerdict = useCallback((ruleId: string, verdict: PolicyVerdict) => {
    setDraft((current) =>
      current === null
        ? current
        : current.map((rule) => (rule.rule_id === ruleId ? { ...rule, verdict } : rule)),
    );
  }, []);

  const publish = useCallback(async () => {
    if (activePolicy === null || draft === null) {
      return;
    }
    const version = newVersion.trim();
    if (version.length === 0) {
      setError("A non-empty version is required to publish.");
      return;
    }
    const doc: PolicyDocument = {
      version,
      default: "deny",
      approval_timeout_seconds: activePolicy.approval_timeout_seconds,
      rules: draft,
    };
    setPublishing(true);
    setError(null);
    setNotice(null);
    try {
      await api.publishPolicy(doc);
      await api.setActivePolicy(version);
      setDraft(null);
      setNewVersion("");
      setNotice(`Published policy ${version} and set it active.`);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPublishing(false);
    }
  }, [activePolicy, draft, newVersion, load]);

  return (
    <div className="catalog-page">
      <div className="page-head">
        <h1>Catalog and policy</h1>
        <PageHelp topic="catalog" />
      </div>

      {error !== null && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      {notice !== null && <div className="notice-banner">{notice}</div>}

      <div className="catalog-layout">
        <section className="panel catalog-panel">
          <h2>Action catalog</h2>
          <div className="catalog-toolbar">
            <label htmlFor="system-filter">Target system</label>
            <select
              id="system-filter"
              value={systemFilter}
              onChange={(e) => setSystemFilter(e.target.value)}
            >
              <option value="">All systems</option>
              {systems.map((system) => (
                <option key={system} value={system}>
                  {system}
                </option>
              ))}
            </select>
            <span className="catalog-count" data-testid="catalog-count">
              {actions === null
                ? "Loading..."
                : `${visible.length} of ${actions.length} actions`}
            </span>
          </div>
          {actions !== null && <CatalogTable actions={visible} />}
        </section>

        <section className="panel policy-panel">
          <h2>Policy</h2>
          {activePolicy === null ? (
            <p className="muted">No active policy loaded.</p>
          ) : (
            <>
              <dl className="policy-summary">
                <dt>Active version</dt>
                <dd data-testid="active-policy-version">{activePolicy.version}</dd>
                <dt>Rules</dt>
                <dd data-testid="active-policy-rule-count">
                  {activePolicy.rules.length} rules
                </dd>
                <dt>Default verdict</dt>
                <dd>
                  <StatusBadge kind="verdict" value="deny" />
                </dd>
                <dt>Approval timeout</dt>
                <dd>{activePolicy.approval_timeout_seconds} s</dd>
                <dt>Known versions</dt>
                <dd>{versions.length > 0 ? versions.join(", ") : "-"}</dd>
              </dl>
              {draft === null ? (
                <button type="button" className="btn btn-primary" onClick={startEditing}>
                  Edit policy
                </button>
              ) : (
                <PolicyEditor
                  draft={draft}
                  newVersion={newVersion}
                  publishing={publishing}
                  onVerdictChange={changeVerdict}
                  onVersionChange={setNewVersion}
                  onPublish={() => void publish()}
                  onCancel={() => setDraft(null)}
                />
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
