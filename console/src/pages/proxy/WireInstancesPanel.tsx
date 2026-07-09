/**
 * WireInstancesPanel — the roster of autonomous instances in the capture.
 *
 * Rendered when NO instance is pinned yet (once one is pinned, the cross-session
 * strip takes over). Lists every instance that emitted flows, with its session
 * count, targets and failures; clicking one deep-links the packet list to that
 * instance (instance -> its wire flows). This is what pulls an orchestration
 * mesh out of the dark: an analyst sees who acted, then drills into one agent.
 * Read-only aggregation (wireInstanceIndex.ts), theme tokens only.
 */

import { useMemo, type JSX } from "react";
import type { WireFlow } from "../../types/platform";
import { indexInstances } from "./wireInstanceIndex";

const _cell = { padding: "0.15rem 0.5rem", fontSize: "0.76rem" } as const;
const _muted = { color: "var(--color-text-muted)" } as const;

export default function WireInstancesPanel({
  flows,
  onPick,
}: {
  flows: WireFlow[];
  /** Pin the packet list to this instance (deep-link). */
  onPick: (instanceId: string) => void;
}): JSX.Element | null {
  const instances = useMemo(() => indexInstances(flows), [flows]);
  // Only meaningful with 2+ instances (a mesh); a single instance adds no signal
  // over the existing per-instance strip.
  if (instances.length < 2) return null;
  return (
    <details className="wire-stats" data-testid="wire-instances">
      <summary>Instances — {instances.length} agents dans la capture</summary>
      <table style={{ borderCollapse: "collapse", width: "100%", margin: "0.4rem 0" }}>
        <tbody>
          {instances.map((i) => (
            <tr key={i.instanceId} data-testid={`wire-instance-${i.instanceId}`}>
              <td style={_cell}>
                <button
                  type="button"
                  className="proxy-wire-step-btn"
                  style={{ font: "inherit", textAlign: "left" }}
                  onClick={() => onPick(i.instanceId)}
                  title={`seq ${i.firstSeq}..${i.lastSeq}`}
                >
                  <code style={{ color: "var(--color-accent)" }}>{i.instanceId}</code>
                </button>
              </td>
              <td style={{ ..._cell, ..._muted, fontVariantNumeric: "tabular-nums" }}>
                {i.sessions} session(s)
              </td>
              <td style={{ ..._cell, ..._muted }}>{i.hosts.join(", ")}</td>
              <td
                style={{
                  ..._cell,
                  textAlign: "right",
                  fontVariantNumeric: "tabular-nums",
                  color: i.fails > 0 ? "var(--badge-red-fg)" : "inherit",
                }}
              >
                {i.count} flux{i.fails > 0 ? ` · ${i.fails} echec(s)` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
