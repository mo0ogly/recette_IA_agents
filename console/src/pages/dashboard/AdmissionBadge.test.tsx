/**
 * AdmissionBadge R16 contract gate.
 *
 * Renders the badge against the REAL captured /runs admission payload
 * (__fixtures__/admission.fixture.json) and asserts the full discriminated
 * union: every admission `status` (trusted | untrusted | unsigned | malformed),
 * both gate `mode`s (observe | enforce), and the admitted true/false rendering.
 * A status the UI does not handle would be a display bug in prod (R16), so each
 * variant is exercised here.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AdmissionVerdict } from "../../types/platform";
import AdmissionBadge from "./AdmissionBadge";
import fixture from "./__fixtures__/admission.fixture.json";

/** Unwrap the admission verdict from a captured /runs response. */
function admissionOf(key: keyof typeof fixture): AdmissionVerdict {
  const entry = fixture[key] as { admission: AdmissionVerdict };
  return entry.admission;
}

describe("AdmissionBadge", () => {
  it("renders every admission status keyed off status alone", () => {
    const statuses: Array<AdmissionVerdict["status"]> = [
      "trusted",
      "untrusted",
      "unsigned",
      "malformed",
    ];
    const byStatus: Record<AdmissionVerdict["status"], keyof typeof fixture> = {
      trusted: "trusted_observe",
      untrusted: "untrusted_observe",
      unsigned: "unsigned_observe",
      malformed: "malformed_observe",
    };
    for (const status of statuses) {
      const { unmount } = render(
        <AdmissionBadge admission={admissionOf(byStatus[status])} />,
      );
      const badge = screen.getByTestId(`admission-badge-${status}`);
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass(`admission-badge-${status}`);
      expect(badge).toHaveTextContent(status);
      unmount();
    }
  });

  it("surfaces the observe mode and admitted for a non-trusted run", () => {
    render(<AdmissionBadge admission={admissionOf("untrusted_observe")} />);
    expect(screen.getByTestId("admission-badge-mode")).toHaveTextContent("observe");
    expect(screen.getByTestId("admission-badge-admitted")).toHaveTextContent(
      "admitted",
    );
  });

  it("surfaces the enforce mode for a trusted run", () => {
    render(<AdmissionBadge admission={admissionOf("trusted_enforce")} />);
    expect(screen.getByTestId("admission-badge-mode")).toHaveTextContent("enforce");
    expect(screen.getByTestId("admission-badge-admitted")).toHaveTextContent(
      "admitted",
    );
  });

  it("renders the denied state for an enforce non-trusted verdict", () => {
    render(<AdmissionBadge admission={admissionOf("untrusted_enforce_denied")} />);
    expect(screen.getByTestId("admission-badge-mode")).toHaveTextContent("enforce");
    expect(screen.getByTestId("admission-badge-admitted")).toHaveTextContent(
      "denied",
    );
  });
});
