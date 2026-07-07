/**
 * Interaction graph page: a multi-agent orchestration run as a directed graph
 * with graph metrics (in/out degree, tool calls, weighted PageRank).
 *
 * Pick an orchestration subject; the page renders its interaction graph (nodes
 * = participants, edges = handoffs weighted by count) plus the per-node metrics.
 * PageRank weighted by handoff volume is an observability/risk signal -- which
 * agent the run actually flows through. Read-only, deterministic (I4).
 */

import { useEffect, useMemo, useState } from "react";

import { getOrchestrationGraph, listSubjects } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import Mermaid from "../../components/help/Mermaid";
import type { OrchestrationGraph } from "../../types/platform";
import "./graph.css";

/** Build a mermaid flowchart from the graph: weighted edges + isolated nodes. */
function toChart(graph: OrchestrationGraph): string {
  const lines = ["flowchart LR"];
  for (const e of graph.edges) {
    lines.push(`  ${e.source} -->|${e.weight}| ${e.target}`);
  }
  const linked = new Set(graph.edges.flatMap((e) => [e.source, e.target]));
  for (const n of graph.nodes) {
    if (!linked.has(n.id)) lines.push(`  ${n.id}`);
  }
  return lines.join("\n");
}

export default function GraphPage(): JSX.Element {
  const [subjects, setSubjects] = useState<string[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [graph, setGraph] = useState<OrchestrationGraph | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSubjects()
      .then((listing) => {
        const orch = listing.subjects
          .filter((s) => s.family === "maf_orchestration")
          .map((s) => s.agent_id);
        setSubjects(orch);
        if (orch.length > 0) setSelected(orch[0]);
      })
      .catch((e: unknown) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (selected === "") return;
    setGraph(null);
    getOrchestrationGraph(selected)
      .then(setGraph)
      .catch((e: unknown) => setError(String(e)));
  }, [selected]);

  const ranked = useMemo(
    () => (graph ? [...graph.nodes].sort((a, b) => b.pagerank - a.pagerank) : []),
    [graph],
  );

  return (
    <section className="page graph-page">
      <div className="page-head">
        <h1>Graphe d&apos;interaction</h1>
        <PageHelp topic="graph" />
        <AssistButton topic="dashboard.overview" label="Graphe d'orchestration" />
      </div>
      <p className="graph-note">
        Un run d&apos;orchestration multi-agent vu comme un <strong>graphe dirige</strong> : noeuds
        = participants, aretes = handoffs (poids = nombre de transferts). Le{" "}
        <strong>PageRank pondere</strong> indique par quel agent le run transite reellement -- un
        signal d&apos;observabilite/risque. Lecture seule, deterministe (I4).
      </p>

      <div className="graph-picker">
        <label htmlFor="graph-subject">Sujet orchestration</label>
        <select
          id="graph-subject"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {subjects.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="graph-error">{error}</p>}

      {graph !== null && (
        <>
          <Mermaid chart={toChart(graph)} title={`Graphe -- ${selected}`} />
          <table className="graph-table" data-testid="graph-metrics">
            <thead>
              <tr>
                <th>agent</th>
                <th>in</th>
                <th>out</th>
                <th>tool calls</th>
                <th>pagerank</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((n) => (
                <tr key={n.id}>
                  <td className="graph-id">{n.id}</td>
                  <td>{n.in_degree}</td>
                  <td>{n.out_degree}</td>
                  <td>{n.tool_calls}</td>
                  <td>{n.pagerank.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
