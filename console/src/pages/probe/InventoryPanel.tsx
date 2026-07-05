/**
 * InventoryPanel -- the discoveryprobe-inventory AgentInventory view.
 *
 * Renders, for every scanned agent: its id, the scanned code EVIDENCE (a shadow
 * agent's derived id can be a bland path component like "repo", so the evidence
 * is what lets the operator identify it -- consumer contract), the PASSPORT
 * BADGE, the ATTESTATION BADGE, the subject kind, and the conformity verdict.
 * The passport badge keys off `passport.kind` (present | absent | invalid),
 * NEVER off a non-empty violations list -- an INVALID passport carries a status
 * but no violation and not_observed conformity, and must still read as invalid
 * (not clean).
 *
 * The attestation badge is a SECOND, ORTHOGONAL axis: it keys off
 * `attestation.kind` (unsigned | trusted | untrusted | malformed) -- the signed
 * `.inspect_ia_agents/passport.json` credential, NOT the manifest. An agent can
 * be a manifest shadow yet carry a trusted credential, or carry a present
 * manifest yet be unsigned; neither axis implies the other, so both badges are
 * shown side by side. The untrusted badge surfaces its typed reasons (WHY), the
 * malformed badge its parse message.
 *
 * Below the table: the violations list (PassportAbsent, UndeclaredHandoff, ...)
 * and the communication graph -- declared vs observed edges, undeclared edges
 * flagged, and via-gateway edges shown separately (a hop through a declared
 * broker is not an undeclared direct handoff).
 *
 * Presentational: receives the inventory as a prop (R16: the contract test
 * renders it against a real captured payload). CSS tokens live in probe.css
 * (no hardcoded colors here).
 */

import type {
  AgentInventory,
  InventoryAgent,
  InventoryAttestation,
  InventoryConformity,
  InventoryEdge,
  InventoryPassport,
  InventoryUntrustReason,
  InventoryViolation,
} from "../../api/client";

/** Human label + badge class for each passport status (keyed off `kind`). */
const PASSPORT_LABEL: Record<InventoryPassport["kind"], string> = {
  present: "present",
  absent: "absent",
  invalid: "invalid",
};

/** Human label for each attestation situation (keyed off `kind`). */
const ATTESTATION_LABEL: Record<InventoryAttestation["kind"], string> = {
  unsigned: "unsigned",
  trusted: "trusted",
  untrusted: "untrusted",
  malformed: "malformed",
};

function PassportBadge({ passport }: { passport: InventoryPassport }): JSX.Element {
  // The badge keys off passport.kind ALONE (never off violations): an invalid
  // passport has no violation but must still read invalid.
  const kind = passport.kind;
  return (
    <span
      className={`inv-badge inv-badge-${kind}`}
      data-testid={`inv-badge-${kind}`}
    >
      {PASSPORT_LABEL[kind]}
    </span>
  );
}

/** One untrust reason as a compact, readable string carrying its distinguishing
 *  field: `scope_overreach` shows the extra scope, `malformed_field` the field. */
function untrustReasonText(reason: InventoryUntrustReason): string {
  switch (reason.kind) {
    case "scope_overreach":
      return `scope_overreach: ${reason.extra.join(", ")}`;
    case "malformed_field":
      return `malformed_field: ${reason.field}`;
    default:
      return reason.kind;
  }
}

/**
 * Signed-attestation badge -- the axis ORTHOGONAL to the manifest PassportBadge.
 *
 * Keyed off `attestation.kind` ALONE (never inferred from anything else): the
 * four states trusted / untrusted / unsigned / malformed each get a distinct
 * badge. `untrusted` renders WHY (its typed reasons, with scope_overreach's
 * extra scope and malformed_field's field), so an operator sees the cause;
 * `malformed` renders the read/parse message. Inline spans only (no block inside
 * a span) to keep the DOM valid. CSS tokens live in probe.css.
 */
function AttestationBadge({
  attestation,
}: {
  attestation: InventoryAttestation;
}): JSX.Element {
  const kind = attestation.kind;
  const className = `inv-attest inv-attest-${kind}`;
  const testid = `inv-attest-${kind}`;

  if (attestation.kind === "untrusted") {
    const reasons = attestation.reasons.map(untrustReasonText);
    return (
      <span className={className} data-testid={testid} title={reasons.join("; ")}>
        <span className="inv-attest-label">{ATTESTATION_LABEL[kind]}</span>
        <span className="inv-attest-reasons">
          {reasons.map((r, i) => (
            <span key={i} className="inv-attest-reason">
              {r}
            </span>
          ))}
        </span>
      </span>
    );
  }

  if (attestation.kind === "malformed") {
    return (
      <span className={className} data-testid={testid} title={attestation.message}>
        <span className="inv-attest-label">{ATTESTATION_LABEL[kind]}</span>
        <span className="inv-attest-message">{attestation.message}</span>
      </span>
    );
  }

  // trusted | unsigned: label only, no reasons to surface.
  return (
    <span className={className} data-testid={testid}>
      <span className="inv-attest-label">{ATTESTATION_LABEL[kind]}</span>
    </span>
  );
}

/** Evidence / identification hint for an agent (a shadow id may be bland). */
function EvidenceCell({ agent }: { agent: InventoryAgent }): JSX.Element {
  const lines: string[] = [];
  if (agent.passport.kind === "absent") lines.push(...agent.passport.evidence);
  else if (agent.passport.kind === "invalid") lines.push(...agent.passport.errors);
  lines.push(...agent.evidence);
  const unique = Array.from(new Set(lines));
  if (unique.length === 0) {
    return <span className="inv-evidence-none">--</span>;
  }
  return (
    <ul className="inv-evidence" style={{ margin: 0, paddingLeft: "1rem" }}>
      {unique.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  );
}

function conformityText(conformity: InventoryConformity): string {
  switch (conformity.kind) {
    case "conform":
      return "conform";
    case "not_observed":
      return "not observed";
    case "violations":
      return `${conformity.violations.length} violation(s)`;
  }
}

/** One violation rendered with its kind and the distinguishing fields. */
function violationDetail(v: InventoryViolation): string {
  if (v.from !== undefined && v.to !== undefined) return `${v.from} -> ${v.to}`;
  if (v.action !== undefined) return `${v.action}${v.source ? ` (${v.source})` : ""}`;
  if (v.declared !== undefined && v.observed !== undefined)
    return `declared ${v.declared} / observed ${v.observed}`;
  if (v.tool !== undefined) return v.tool;
  return "";
}

function EdgeGroup({
  label,
  edges,
  variant,
  testid,
}: {
  label: string;
  edges: InventoryEdge[];
  variant?: "undeclared" | "gateway";
  testid: string;
}): JSX.Element {
  const edgeClass =
    variant === "undeclared"
      ? "inv-edge inv-edge-undeclared"
      : variant === "gateway"
        ? "inv-edge inv-edge-gateway"
        : "inv-edge";
  return (
    <div className="inv-edge-group" data-testid={testid}>
      <span className="inv-edge-group-label">
        {label} ({edges.length})
      </span>
      {edges.length === 0 ? (
        <span className="inv-empty">none</span>
      ) : (
        edges.map((e, i) => (
          <span key={`${e.from}->${e.to}-${i}`} className={edgeClass}>
            {e.from} -&gt; {e.to}
          </span>
        ))
      )}
    </div>
  );
}

export default function InventoryPanel({
  inventory,
  live = false,
  reason = null,
}: {
  inventory: AgentInventory | null;
  /** True when the inventory is a live on-demand scan; false when it is the
   *  committed sample fallback (Rust engine not built). */
  live?: boolean;
  /** Why the scan fell back to the sample, when `live` is false. */
  reason?: string | null;
}): JSX.Element | null {
  if (inventory === null) return null;

  // Flatten every agent's violations, each carrying its owning agent id.
  const violations: Array<{ agent_id: string; violation: InventoryViolation }> = [];
  for (const agent of inventory.agents) {
    if (agent.conformity.kind === "violations") {
      for (const v of agent.conformity.violations) {
        violations.push({ agent_id: agent.agent_id, violation: v });
      }
    }
  }

  const graph = inventory.comm_graph;

  return (
    <section className="inv-panel" data-testid="inv-panel">
      <h4 className="inv-title">
        Agent inventory -- static scan + correlation
        <span
          className={live ? "inv-live-badge inv-live-on" : "inv-live-badge inv-live-off"}
          data-testid="inv-live-badge"
          title={live ? "Live scan of the configured agent-source trees" : (reason ?? "")}
        >
          {live ? "LIVE SCAN" : "SAMPLE"}
        </span>
      </h4>

      <div className="inv-summary" data-testid="inv-summary">
        <span>with passport: {inventory.summary.with_passport}</span>
        <span>without passport: {inventory.summary.without_passport}</span>
        <span>invalid passport: {inventory.summary.invalid_passport}</span>
        <span>violations: {inventory.summary.violation_count}</span>
        <span>attested trusted: {inventory.summary.attested_trusted}</span>
        <span>attested untrusted: {inventory.summary.attested_untrusted}</span>
        <span>unsigned: {inventory.summary.unsigned}</span>
        <span>attested malformed: {inventory.summary.attested_malformed}</span>
      </div>

      <table className="inv-table" data-testid="inv-agents-table">
        <thead>
          <tr>
            <th>agent_id</th>
            <th>passport</th>
            <th>attestation</th>
            <th>kind</th>
            <th>conformity</th>
            <th>evidence</th>
          </tr>
        </thead>
        <tbody>
          {inventory.agents.map((agent, i) => (
            <tr
              key={`${agent.agent_id}-${i}`}
              data-testid={`inv-agent-row-${i}`}
            >
              <td className="inv-agent-id">{agent.agent_id}</td>
              <td>
                <PassportBadge passport={agent.passport} />
              </td>
              <td>
                <AttestationBadge attestation={agent.attestation} />
              </td>
              <td>{agent.kind ?? "--"}</td>
              <td className="inv-conformity">{conformityText(agent.conformity)}</td>
              <td>
                <EvidenceCell agent={agent} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div>
        <h5 className="inv-edge-group-label">Violations</h5>
        {violations.length === 0 ? (
          <span className="inv-empty">no violation</span>
        ) : (
          <div className="inv-violations" data-testid="inv-violations">
            {violations.map(({ agent_id, violation }, i) => (
              <div
                key={`${agent_id}-${violation.kind}-${i}`}
                className="inv-violation"
                data-testid={`inv-violation-${violation.kind}`}
              >
                <span className="inv-violation-kind">{violation.kind}</span>
                <span className="inv-agent-id">{agent_id}</span>
                <span className="inv-violation-detail">
                  {violationDetail(violation)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="inv-graph" data-testid="inv-comm-graph">
        <h5 className="inv-edge-group-label">Communication graph</h5>
        <EdgeGroup label="declared" edges={graph.declared_edges} testid="inv-edges-declared" />
        <EdgeGroup label="observed" edges={graph.observed_edges} testid="inv-edges-observed" />
        <EdgeGroup
          label="undeclared"
          edges={graph.undeclared_edges}
          variant="undeclared"
          testid="inv-edges-undeclared"
        />
        <EdgeGroup
          label="via gateway"
          edges={graph.via_gateway_edges}
          variant="gateway"
          testid="inv-edges-gateway"
        />
      </div>
    </section>
  );
}
