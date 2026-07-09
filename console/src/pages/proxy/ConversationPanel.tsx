/**
 * ConversationPanel -- the "sophisticated Wireshark for agents" source.
 *
 * For ANY run (any agent, any campaign) it shows ONE ordered conversation that
 * joins what the LLM DECIDED at each step (thought: kind, tool, intent, tokens
 * -- GET /capture/llm-traces) with the request the agent sent to the server AND
 * the server's response (GET /proxy/traces). The merge is the pure
 * buildRunConversation; this panel only picks a run, fetches, and renders.
 *
 * Read-only. The run picker lists every run (RunSummary carries agent_id +
 * campaign_id), so present and future agents/campaigns appear automatically.
 * The full raw LLM message text lives on the wire overlay (WirePanel) when it is
 * on; this view needs only the always-available capture + proxy traces.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { getLlmTraces, getProxyTraces, listRuns } from "../../api/client";
import type { RunSummary } from "../../types/platform";
import type { SourcePanelProps } from "./proxyMenu";
import { buildRunConversation, type ConversationTurn } from "./runConversation";

/** A short, recognisable label for a run: id head + agent + campaign + status. */
function runLabel(r: RunSummary): string {
  const bits = [r.id.slice(0, 8)];
  if (r.agent_id) bits.push(r.agent_id);
  if (r.campaign_id) bits.push(`[${r.campaign_id}]`);
  bits.push(r.status);
  return bits.join(" · ");
}

export default function ConversationPanel({ onStatus }: SourcePanelProps): JSX.Element {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run") ?? "";
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch(() => setRuns([]));
  }, []);

  const setRun = useCallback(
    (value: string): void => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) {
            next.set("run", value);
          } else {
            next.delete("run");
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  useEffect(() => {
    if (runId === "") {
      setTurns([]);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    // Both halves of the run's story: the LLM decisions and the server exchanges.
    Promise.all([getLlmTraces(runId), getProxyTraces(undefined, runId)])
      .then(([llm, proxy]) => {
        if (alive) {
          setTurns(buildRunConversation(llm.traces, proxy.traces));
        }
      })
      .catch((e: unknown) => {
        if (alive) {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [runId]);

  const failed = useMemo(
    () => turns.filter((t) => t.exchange !== null && !t.exchange.ok).length,
    [turns],
  );

  useEffect(() => {
    onStatus?.({ count: turns.length, failed });
  }, [turns.length, failed, onStatus]);

  return (
    <section className="proxy-conversation" data-testid="conversation-panel">
      <header className="proxy-header">
        <label className="proxy-filter-label">
          run
          <select
            className="proxy-filter-input"
            data-testid="conversation-run"
            value={runId}
            onChange={(e) => setRun(e.target.value)}
          >
            <option value="">-- choisir un run --</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {runLabel(r)}
              </option>
            ))}
          </select>
        </label>
        <span className="proxy-summary">
          {turns.length} etapes{failed > 0 ? ` (${failed} KO)` : ""}
        </span>
      </header>

      {error !== null && <p className="proxy-error">{error}</p>}

      {runId === "" ? (
        <p className="proxy-banner" role="status" data-testid="conversation-hint">
          Choisir un run pour voir la conversation : la pensee du LLM a chaque
          etape, la requete envoyee au serveur, et la reponse du serveur.
        </p>
      ) : loading ? (
        <p className="proxy-viewer-msg">chargement...</p>
      ) : turns.length === 0 ? (
        <p className="proxy-empty" data-testid="conversation-empty">
          aucune conversation pour ce run (ni decision LLM ni echange serveur --
          capture branchee et proxy-debug actifs ?)
        </p>
      ) : (
        <ol className="proxy-conv-list" data-testid="conversation-list">
          {turns.map((t) => (
            <li key={t.seq} className="proxy-conv-turn" data-testid={`conv-turn-${t.seq}`}>
              <span className="proxy-conv-step">#{t.step}</span>
              {t.decisionKind !== null && (
                <div className="proxy-conv-think" data-testid={`conv-think-${t.seq}`}>
                  <span className="proxy-conv-tag">
                    pensee{t.model !== null ? ` (${t.model})` : ""}
                  </span>
                  <span className="proxy-conv-decision">
                    {t.decisionKind}
                    {t.tool !== null ? ` -> ${t.tool}` : ""}
                  </span>
                  {t.intent !== null && <span className="proxy-conv-intent">{t.intent}</span>}
                  {t.tokens !== null && (
                    <span className="proxy-conv-tokens">
                      {t.tokens.prompt} {"->"} {t.tokens.completion} tok
                    </span>
                  )}
                </div>
              )}
              {t.exchange !== null && (
                <div
                  className="proxy-conv-exchange"
                  data-testid={`conv-exchange-${t.seq}`}
                  data-ok={t.exchange.ok}
                >
                  <div className="proxy-conv-req">
                    <span className="proxy-conv-tag">requete</span>
                    <span>
                      {t.exchange.actionType} {t.exchange.resource}
                    </span>
                    <pre className="proxy-conv-body">{JSON.stringify(t.exchange.request)}</pre>
                  </div>
                  <div className="proxy-conv-resp">
                    <span className="proxy-conv-tag">reponse serveur ({t.exchange.status})</span>
                    <pre className="proxy-conv-body">{JSON.stringify(t.exchange.response)}</pre>
                    {t.exchange.error !== null && (
                      <span className="proxy-conv-err">{t.exchange.error}</span>
                    )}
                  </div>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
