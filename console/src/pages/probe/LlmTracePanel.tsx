/**
 * The in-process hook capture, per run: each LLM decision's intent + the
 * operational metrics (tokens, latency, error). This is the HOOK surface half of
 * the multi-surface view -- complementary to the eBPF wire surface, reconciled in
 * the detection scorecard. Presentational: the parent supplies the traces.
 */

import type { LlmTrace } from "../../api/client";

export default function LlmTracePanel({ traces }: { traces: LlmTrace[] }): JSX.Element {
  if (traces.length === 0) {
    return (
      <p className="probe-trace-empty" data-testid="llm-trace-empty">
        Aucune trace LLM capturee (surface hook in-process).
      </p>
    );
  }
  return (
    <div className="probe-trace" data-testid="llm-trace-panel">
      <table className="probe-trace-table">
        <thead>
          <tr>
            <th>Intention</th>
            <th>Tokens</th>
            <th>Latence</th>
            <th>Etat</th>
          </tr>
        </thead>
        <tbody>
          {traces.map((t) => (
            <tr key={t.event_id} data-testid={`llm-trace-${t.event_id}`}>
              <td className="probe-trace-intent">
                {t.kind === "tool_call" ? t.intent : "(reflexion)"}
              </td>
              <td>{t.total_tokens}</td>
              <td>{t.latency_ms} ms</td>
              <td className={t.error ? "probe-trace-err" : "probe-trace-ok"}>
                {t.error ?? "ok"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
