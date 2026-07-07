/**
 * Recette page -- run the discovery and identification recettes and score the
 * tool under test against the ground-truth corpus.
 *
 * This is where the loop closes: the cockpit launches test agents, and here we
 * run the discovery / identification runner over the corpus and read its
 * scorecard (detected? distinguished? verdict == ground-truth?). The runners
 * stream per-item results then a final scorecard frame.
 */

import { launchRunner } from "../../api/client";
import { useRunStream } from "../../hooks/useRunStream";
import type { RunFrame } from "../../hooks/useRunStream";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import "./recette.css";

interface ScorecardData {
  total?: number;
  passed?: number;
  false_positives?: number;
  false_negatives?: number;
  detection_rate?: number;
  all_passed?: boolean;
  surface?: string;
}

function isScorecard(f: RunFrame): boolean {
  return f.type === "scorecard";
}

function summaryFrames(frames: RunFrame[]): ScorecardData[] {
  return frames.filter(isScorecard).map((f) => f.data as ScorecardData);
}

function Pill({ ok, label }: { ok: boolean; label: string }): JSX.Element {
  return <span className={`pill ${ok ? "pill-ok" : "pill-bad"}`}>{label}</span>;
}

export default function RecettePage(): JSX.Element {
  const discovery = useRunStream();
  const identification = useRunStream();

  const discoveryCards = summaryFrames(discovery.frames);
  const identAgents = identification.frames.filter((f) => f.type === "agent_result");
  const identCard = summaryFrames(identification.frames)[0];

  return (
    <div>
      <div className="page-head">
        <h1>Recette -- discovery &amp; identification</h1>
        <PageHelp topic="recette" />
        <AssistButton topic="verdicts.recent" label="Recette d'identification" />
      </div>

      <div className="recette-grid">
        <section className="panel">
          <div className="recette-head">
            <h2>Discovery</h2>
            <div className="recette-actions">
              <button
                type="button"
                onClick={() => void discovery.start(() => launchRunner("discovery"))}
                disabled={discovery.running}
              >
                Lancer discovery
              </button>
              <button
                type="button"
                className="recette-stop"
                onClick={() => void discovery.stop()}
                disabled={!discovery.running}
              >
                Arreter
              </button>
            </div>
          </div>
          {discovery.error !== null && (
            <div className="recette-error" role="alert">
              {discovery.error}
            </div>
          )}
          {discovery.runId !== null && (
            <p className="recette-status">
              {discovery.runId} -- {discovery.status}
            </p>
          )}
          {discoveryCards.length === 0 ? (
            <p className="recette-empty">
              Lance la recette discovery sur le corpus de repos (par surface).
            </p>
          ) : (
            <table className="recette-table">
              <thead>
                <tr>
                  <th>Surface</th>
                  <th>Total</th>
                  <th>Passed</th>
                  <th>FP</th>
                  <th>FN</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {discoveryCards.map((c) => (
                  <tr key={c.surface ?? "?"}>
                    <td>{c.surface ?? "?"}</td>
                    <td>{c.total ?? 0}</td>
                    <td>{c.passed ?? 0}</td>
                    <td>{c.false_positives ?? 0}</td>
                    <td>{c.false_negatives ?? 0}</td>
                    <td>
                      <Pill ok={c.all_passed === true} label={c.all_passed ? "PASS" : "FAIL"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel">
          <div className="recette-head">
            <h2>Identification</h2>
            <div className="recette-actions">
              <button
                type="button"
                onClick={() => void identification.start(() => launchRunner("identification"))}
                disabled={identification.running}
              >
                Lancer identification
              </button>
              <button
                type="button"
                className="recette-stop"
                onClick={() => void identification.stop()}
                disabled={!identification.running}
              >
                Arreter
              </button>
            </div>
          </div>
          {identification.error !== null && (
            <div className="recette-error" role="alert">
              {identification.error}
            </div>
          )}
          {identCard && (
            <p className="recette-summary">
              {identCard.passed}/{identCard.total} agents -- detection rate{" "}
              {((identCard.detection_rate ?? 0) * 100).toFixed(0)}% --{" "}
              <Pill ok={identCard.all_passed === true} label={identCard.all_passed ? "PASS" : "FAIL"} />
            </p>
          )}
          {identAgents.length === 0 ? (
            <p className="recette-empty">
              Lance la recette identification sur le corpus d'agents (correct + incorrect).
            </p>
          ) : (
            <table className="recette-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Predit</th>
                  <th>Attendu</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {identAgents.map((f) => {
                  const d = f.data as {
                    agent_id?: string;
                    passed?: boolean;
                    predicted_verdict?: string;
                    expected_verdict?: string;
                  };
                  return (
                    <tr key={f.seq}>
                      <td>{d.agent_id}</td>
                      <td>{d.predicted_verdict}</td>
                      <td>{d.expected_verdict}</td>
                      <td>
                        <Pill ok={d.passed === true} label={d.passed ? "PASS" : "FAIL"} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
