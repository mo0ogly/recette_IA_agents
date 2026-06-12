import { render, screen, cleanup } from "@testing-library/react";
import { StatusBadge, assertNever } from "./StatusBadge";
import type { ApprovalState, PolicyVerdict, RiskLevel } from "../types/platform";

const VERDICTS: PolicyVerdict[] = ["allow", "deny", "escalate"];
const APPROVAL_STATES: ApprovalState[] = ["none", "pending", "approved", "denied", "timeout"];
const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high", "critical"];

describe("StatusBadge", () => {
  it.each(VERDICTS)("renders verdict %s with its badge class", (value) => {
    render(<StatusBadge kind="verdict" value={value} />);
    const el = screen.getByText(value);
    expect(el).toBeInTheDocument();
    expect(el).toHaveClass("badge", `badge-${value}`);
    cleanup();
  });

  it.each(APPROVAL_STATES)("renders approval state %s with its badge class", (value) => {
    render(<StatusBadge kind="approval" value={value} />);
    const el = screen.getByText(value);
    expect(el).toBeInTheDocument();
    expect(el).toHaveClass("badge", `badge-${value}`);
    cleanup();
  });

  it.each(RISK_LEVELS)("renders risk level %s with its badge class", (value) => {
    render(<StatusBadge kind="risk" value={value} />);
    const el = screen.getByText(value);
    expect(el).toBeInTheDocument();
    expect(el).toHaveClass("badge", `badge-${value}`);
    cleanup();
  });
});

// ---------------------------------------------------------------------------
// Type-level exhaustiveness checks: these functions fail compilation (through
// assertNever's `never` parameter) if a variant is ever added to the union
// without being handled here.
// ---------------------------------------------------------------------------

function verdictLabel(v: PolicyVerdict): string {
  switch (v) {
    case "allow":
      return "Allow";
    case "deny":
      return "Deny";
    case "escalate":
      return "Escalate";
    default:
      return assertNever(v);
  }
}

function approvalLabel(s: ApprovalState): string {
  switch (s) {
    case "none":
      return "None";
    case "pending":
      return "Pending";
    case "approved":
      return "Approved";
    case "denied":
      return "Denied";
    case "timeout":
      return "Timeout";
    default:
      return assertNever(s);
  }
}

describe("union exhaustiveness", () => {
  it("covers every PolicyVerdict variant", () => {
    expect(VERDICTS.map(verdictLabel)).toEqual(["Allow", "Deny", "Escalate"]);
  });

  it("covers every ApprovalState variant", () => {
    expect(APPROVAL_STATES.map(approvalLabel)).toEqual([
      "None",
      "Pending",
      "Approved",
      "Denied",
      "Timeout",
    ]);
  });
});
