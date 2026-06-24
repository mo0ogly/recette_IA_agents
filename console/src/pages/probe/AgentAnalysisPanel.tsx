/**
 * AgentAnalysisPanel -- the discovery's REPORT in the integrated console.
 *
 * The discovery's job is to IDENTIFY each agent and compare, in detail, what it
 * was PLANNED to do (declared scope + bound server), what it SAID it would do
 * (the decided action-log, when linked) and what it DID (the kernel wire the eBPF
 * probe saw), then SAY WHAT TO LOG. This panel renders that per-agent report:
 * the three-way columns, a coherent/divergent verdict, and the logging
 * recommendations tiered alert | warn | info. Read-only; the analysis is
 * deterministic (I4), computed server-side in recette/surface/agent_analysis.py.
 */

import type { AgentAnalysis } from "../../api/client";

function Column({ title, items }: { title: string; items: string[] }): JSX.Element {
  return (
    <div className="aa-col">
      <h5 className="aa-col-title">{title}</h5>
      {items.length === 0 ? (
        <span className="aa-col-empty">none</span>
      ) : (
        <ul className="aa-col-list">
          {items.map((it) => (
            <li key={it}>{it}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AgentReport({ a }: { a: AgentAnalysis }): JSX.Element {
  const done: string[] = [
    ...a.done.dialed_servers.map((s) => `dial ${s}`),
    ...a.done.undeclared_egress.map((s) => `EGRESS ${s}`),
    ...a.done.undeclared_dns.map((s) => `DNS ${s}`),
    ...(a.done.process_spawned ? ["spawned a child process"] : []),
    ...a.done.sensitive_opens.map((p) => `open ${p}`),
  ];
  return (
    <article className="aa-agent" data-testid={`aa-agent-${a.agent_id}`}>
      <header className="aa-head">
        <span className="aa-id">{a.agent_id}</span>
        <span
          className={`aa-verdict ${a.coherent ? "aa-ok" : "aa-divergent"}`}
          data-testid={`aa-verdict-${a.agent_id}`}
        >
          {a.coherent ? "coherent" : "DIVERGENT"}
        </span>
        {!a.identified && <span className="aa-verdict aa-divergent">not identified</span>}
      </header>

      <p className="aa-analysis">{a.analysis}</p>

      <div className="aa-cols">
        <Column title="PLANNED (declared)" items={[...a.planned.systems, ...a.planned.scope]} />
        <Column title="SAID (decided)" items={a.said ? a.said.actions : ["(no linked action-log)"]} />
        <Column title="DONE (kernel saw)" items={done} />
      </div>

      <div className="aa-recs">
        <h5 className="aa-col-title">What to log</h5>
        <ul className="aa-rec-list">
          {a.logging_recommendations.map((r, i) => (
            <li key={`${r.severity}-${i}`} className={`aa-rec aa-rec-${r.severity}`}>
              <span className="aa-sev">{r.severity.toUpperCase()}</span>
              <span className="aa-rec-log">{r.log}</span>
              <span className="aa-rec-why">{r.why}</span>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}

export default function AgentAnalysisPanel({
  analysis,
}: {
  analysis?: AgentAnalysis[];
}): JSX.Element | null {
  if (!analysis || analysis.length === 0) return null;
  return (
    <section className="aa-panel" data-testid="agent-analysis-panel">
      <h4 className="aa-panel-title">
        Discovery analysis -- planned vs said vs done, and what to log
      </h4>
      {analysis.map((a) => (
        <AgentReport key={a.agent_id} a={a} />
      ))}
    </section>
  );
}
