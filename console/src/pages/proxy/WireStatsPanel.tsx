/**
 * WireStatsPanel — the "Statistics" view for captured agent traffic (defensive).
 *
 * A collapsible summary over the currently visible flows: protocol hierarchy
 * (share of flows carrying each dissected layer), endpoint hierarchy (top hosts),
 * and a token accounting rolled up per autonomous instance. Read-only aggregation
 * (wireStats.ts) — it only counts what was captured. Styling is inline with theme
 * tokens to avoid touching the shared proxy.css.
 */

import { useMemo, type JSX } from "react";
import type { WireFlow } from "../../types/platform";
import { computeWireStats } from "./wireStats";

const _cell = { padding: "0.15rem 0.5rem", fontSize: "0.76rem" } as const;
const _muted = { color: "var(--color-text-muted)" } as const;

function Bar({ share }: { share: number }): JSX.Element {
  return (
    <span
      style={{
        display: "inline-block",
        height: "6px",
        width: `${Math.round(share * 100)}%`,
        minWidth: share > 0 ? "2px" : 0,
        background: "var(--color-accent)",
        borderRadius: "2px",
        verticalAlign: "middle",
      }}
    />
  );
}

export default function WireStatsPanel({ flows }: { flows: WireFlow[] }): JSX.Element | null {
  const stats = useMemo(() => computeWireStats(flows), [flows]);
  if (stats.totalFlows === 0) return null;
  return (
    <details className="wire-stats" data-testid="wire-stats">
      <summary>
        Statistiques — {stats.totalFlows} flux, {stats.fails} échec(s),{" "}
        {stats.tokensTotal.input + stats.tokensTotal.output} tokens
      </summary>
      <div style={{ display: "grid", gap: "0.75rem", padding: "0.5rem 0" }}>
        <section data-testid="wire-stats-protocols">
          <div style={{ ..._muted, fontSize: "0.74rem", marginBottom: "0.2rem" }}>
            Hiérarchie de protocole
          </div>
          {stats.protocols.map((p) => (
            <div key={p.layer} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <code style={{ ..._cell, width: "3.5rem" }}>{p.layer}</code>
              <span style={{ flex: "1 1 auto" }}>
                <Bar share={p.share} />
              </span>
              <span style={{ ..._cell, ..._muted, fontVariantNumeric: "tabular-nums" }}>
                {p.flows} ({Math.round(p.share * 100)}%)
              </span>
            </div>
          ))}
        </section>

        <section data-testid="wire-stats-endpoints">
          <div style={{ ..._muted, fontSize: "0.74rem", marginBottom: "0.2rem" }}>Endpoints</div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              {stats.endpoints.map((e) => (
                <tr key={e.host}>
                  <td style={_cell}>
                    <code>{e.host}</code>
                  </td>
                  <td style={{ ..._cell, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {e.flows}
                  </td>
                  <td style={{ ..._cell, textAlign: "right", color: e.fails > 0 ? "var(--badge-red-fg)" : "inherit" }}>
                    {e.fails > 0 ? `${e.fails} échec(s)` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {stats.tokensByInstance.length > 0 && (
          <section data-testid="wire-stats-tokens">
            <div style={{ ..._muted, fontSize: "0.74rem", marginBottom: "0.2rem" }}>
              Tokens par instance
            </div>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <tbody>
                {stats.tokensByInstance.map((t) => (
                  <tr key={t.instance}>
                    <td style={_cell}>
                      <code>{t.instance}</code>{" "}
                      <span style={_muted}>{t.model ?? ""}</span>
                    </td>
                    <td style={{ ..._cell, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      in {t.input} / out {t.output}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </div>
    </details>
  );
}
