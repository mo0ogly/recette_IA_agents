/**
 * WireFilterBar — the wire panel's filter controls (extracted for the size ceiling).
 *
 * The fixed-field controls (host / method / status / run / instance / session /
 * free text) drive the SERVER query; the Wireshark-style DISPLAY FILTER (df) is a
 * client-side predicate over the dissected fields (wireFilter.ts) shown with its
 * parse error when invalid. Same testids/structure as before so the panel's
 * contract tests are unaffected. Presentational: all state lives in the URL via
 * setParam.
 */

import type { JSX } from "react";
import TrackingFilters from "./TrackingFilters";
import type { WireFlowFilter } from "./wireFlowModel";

export default function WireFilterBar({
  filter,
  setParam,
  hosts,
  methods,
  runIds,
  dfError,
}: {
  filter: WireFlowFilter;
  setParam: (key: string, value: string) => void;
  hosts: string[];
  methods: string[];
  runIds: string[];
  dfError: string | null;
}): JSX.Element {
  return (
    <div className="proxy-filter" role="group" aria-label="wire filter">
      <label className="proxy-filter-label">
        host
        <select
          className="proxy-filter-input"
          value={filter.host ?? ""}
          onChange={(e) => setParam("host", e.target.value)}
        >
          <option value="">tous</option>
          {hosts.map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
      </label>
      <label className="proxy-filter-label">
        method
        <select
          className="proxy-filter-input"
          value={filter.method ?? ""}
          onChange={(e) => setParam("method", e.target.value)}
        >
          <option value="">toutes</option>
          {methods.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label className="proxy-filter-label">
        status
        <input
          className="proxy-filter-input"
          type="text"
          data-testid="wire-filter-status"
          value={filter.status ?? ""}
          onChange={(e) => setParam("status", e.target.value)}
        />
      </label>
      <label className="proxy-filter-label">
        run_id
        {/* `run` is page-owned (cockpit deep-link): READ to narrow, only ever SET
            (never deleted), so an empty selection is a no-op. */}
        <select
          className="proxy-filter-input"
          value={filter.runId ?? ""}
          onChange={(e) => {
            if (e.target.value) {
              setParam("run", e.target.value);
            }
          }}
        >
          <option value="">tous</option>
          {runIds.map((r) => (
            <option key={r} value={r}>
              {r.slice(0, 12)}
            </option>
          ))}
        </select>
      </label>
      <TrackingFilters
        instanceId={filter.instanceId}
        sessionId={filter.sessionId}
        setParam={setParam}
      />
      <label className="proxy-filter-label">
        texte
        <input
          className="proxy-filter-input"
          type="text"
          data-testid="wire-filter-text"
          value={filter.text ?? ""}
          onChange={(e) => setParam("q", e.target.value)}
        />
      </label>
      {/* Wireshark-style display filter over dissected L3-L8 fields (client-side). */}
      <label className="proxy-filter-label proxy-filter-df">
        display filter
        <input
          className="proxy-filter-input"
          type="text"
          data-testid="wire-filter-df"
          placeholder='tls.ja3 == aaa && l8.tool contains "delete"'
          value={filter.df ?? ""}
          onChange={(e) => setParam("df", e.target.value)}
          aria-invalid={dfError !== null}
        />
        {dfError !== null && (
          <span
            className="proxy-df-error"
            data-testid="wire-filter-df-error"
            style={{ color: "var(--badge-red-fg)", fontSize: "0.72rem" }}
          >
            {dfError}
          </span>
        )}
      </label>
    </div>
  );
}
