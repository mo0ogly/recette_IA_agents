/**
 * AdmissionBadge -- the passport-admission verdict of a lane_b launch.
 *
 * Legibility-first (CLAUDE.md): when a launch returns an admission that is NOT
 * trusted, the operator must SEE why the passport is suspect even though the run
 * proceeded (observe mode). The badge keys off `admission.status` ALONE -- the
 * four states trusted / untrusted / unsigned / malformed each get a distinct,
 * token-driven style (green / red / neutral / amber), mirroring the probe
 * AttestationBadge. It also surfaces the gate `mode` (observe | enforce) and
 * whether the agent was `admitted`, so a non-trusted-but-observed run reads as a
 * WARN (the run happened, the passport is not trusted).
 *
 * Enforce-mode denial never reaches this badge: a non-trusted agent gets a 403
 * at the API boundary and no RunHandle, so the denial is surfaced at the call
 * site (dashboard error banner), not here.
 *
 * Presentational: receives the verdict as a prop (R16: AdmissionBadge.test.tsx
 * renders it against a real captured payload, covering all four statuses + both
 * modes + admitted true/false). CSS tokens live in dashboard.css (no hardcoded
 * colors here).
 */

import type { AdmissionVerdict } from "../../types/platform";

/** Human label for each admission status (keyed off `status`). */
const ADMISSION_LABEL: Record<AdmissionVerdict["status"], string> = {
  trusted: "trusted",
  untrusted: "untrusted",
  unsigned: "unsigned",
  malformed: "malformed",
};

export default function AdmissionBadge({
  admission,
}: {
  admission: AdmissionVerdict;
}): JSX.Element {
  const { status, mode, admitted } = admission;
  const admittedLabel = admitted ? "admitted" : "denied";
  return (
    <span
      className={`admission-badge admission-badge-${status}`}
      data-testid={`admission-badge-${status}`}
      title={`passport admission: ${status} -- mode ${mode} -- ${admittedLabel}`}
    >
      <span className="admission-badge-label">{ADMISSION_LABEL[status]}</span>
      <span className="admission-badge-mode" data-testid="admission-badge-mode">
        {mode}
      </span>
      <span className="admission-badge-admitted" data-testid="admission-badge-admitted">
        {admittedLabel}
      </span>
    </span>
  );
}
