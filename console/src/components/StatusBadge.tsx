import type { ApprovalState, PolicyVerdict, RiskLevel } from "../types/platform";

/**
 * Discriminated props: a badge renders exactly one variant of one union.
 * Each switch below is exhaustive; adding a variant to a union breaks
 * compilation through assertNever.
 */
export type StatusBadgeProps =
  | { kind: "verdict"; value: PolicyVerdict }
  | { kind: "approval"; value: ApprovalState }
  | { kind: "risk"; value: RiskLevel };

/** Compile-time exhaustiveness guard for discriminated unions. */
export function assertNever(value: never): never {
  throw new Error(`Unhandled variant: ${String(value)}`);
}

function verdictClass(value: PolicyVerdict): string {
  switch (value) {
    case "allow":
      return "badge-allow";
    case "deny":
      return "badge-deny";
    case "escalate":
      return "badge-escalate";
    default:
      return assertNever(value);
  }
}

function approvalClass(value: ApprovalState): string {
  switch (value) {
    case "none":
      return "badge-none";
    case "pending":
      return "badge-pending";
    case "approved":
      return "badge-approved";
    case "denied":
      return "badge-denied";
    case "timeout":
      return "badge-timeout";
    default:
      return assertNever(value);
  }
}

function riskClass(value: RiskLevel): string {
  switch (value) {
    case "low":
      return "badge-low";
    case "medium":
      return "badge-medium";
    case "high":
      return "badge-high";
    case "critical":
      return "badge-critical";
    default:
      return assertNever(value);
  }
}

function badgeClass(props: StatusBadgeProps): string {
  switch (props.kind) {
    case "verdict":
      return verdictClass(props.value);
    case "approval":
      return approvalClass(props.value);
    case "risk":
      return riskClass(props.value);
    default:
      return assertNever(props);
  }
}

export function StatusBadge(props: StatusBadgeProps): JSX.Element {
  return <span className={`badge ${badgeClass(props)}`}>{props.value}</span>;
}
