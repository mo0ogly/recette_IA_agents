/**
 * WireExpertPanel — the "Expert Information" view over captured agent traffic
 * (defensive conformance audit, Wireshark-style).
 *
 * A collapsible list of the expert-info signals computed by wireExpert.ts on
 * the currently visible flows: unmasked secret in a body, JA3 drift within an
 * instance, TLS downgrade, server error. Each signal is clickable and opens
 * the flow it is anchored on (like Wireshark's expert dialog jumping to the
 * packet). Pure display: read-only over the capture, theme tokens only.
 */

import { useMemo, type JSX } from "react";
import type { WireFlow } from "../../types/platform";
import { computeExpertInfo, expertSummary, type ExpertSeverity } from "./wireExpert";

const _cell = { padding: "0.15rem 0.5rem", fontSize: "0.76rem" } as const;
const _muted = { color: "var(--color-text-muted)" } as const;

const _SEV_LABEL: Record<ExpertSeverity, string> = {
  error: "erreur",
  warn: "alerte",
  note: "note",
};

const _SEV_COLOR: Record<ExpertSeverity, string> = {
  error: "var(--badge-red-fg)",
  warn: "var(--badge-amber-fg)",
  note: "var(--color-text-muted)",
};

export default function WireExpertPanel({
  flows,
  onPick,
}: {
  flows: WireFlow[];
  /** Open the flow a signal is anchored on (selection in the parent panel). */
  onPick: (seq: number) => void;
}): JSX.Element | null {
  const signals = useMemo(() => computeExpertInfo(flows), [flows]);
  if (signals.length === 0) return null;
  const summary = expertSummary(signals);
  return (
    <details className="wire-stats" data-testid="wire-expert">
      <summary>
        Info expert — {signals.length} signal(aux)
        {summary.error > 0 ? `, ${summary.error} erreur(s)` : ""}
        {summary.warn > 0 ? `, ${summary.warn} alerte(s)` : ""}
        {summary.note > 0 ? `, ${summary.note} note(s)` : ""}
      </summary>
      <table style={{ borderCollapse: "collapse", width: "100%", margin: "0.4rem 0" }}>
        <tbody>
          {signals.map((s) => (
            <tr key={`${s.kind}-${s.seq}`} data-testid={`wire-expert-${s.kind}-${s.seq}`}>
              <td style={{ ..._cell, color: _SEV_COLOR[s.severity], whiteSpace: "nowrap" }}>
                {_SEV_LABEL[s.severity]}
              </td>
              <td style={{ ..._cell, whiteSpace: "nowrap" }}>
                <code>{s.kind}</code>
              </td>
              <td style={_cell}>
                <button
                  type="button"
                  className="proxy-wire-step-btn"
                  style={{ font: "inherit", textAlign: "left" }}
                  onClick={() => onPick(s.seq)}
                >
                  <span style={{ ..._muted, marginRight: "0.4rem" }}>#{s.seq}</span>
                  {s.message}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
